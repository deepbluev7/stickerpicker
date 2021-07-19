# maunium-stickerpicker - A fast and simple Matrix sticker picker widget.
# Copyright (C) 2020 Tulir Asokan
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from typing import Dict
import argparse
import asyncio
import os.path
import json
import re

from telethon import TelegramClient
from telethon.tl.functions.messages import GetAllStickersRequest, GetStickerSetRequest
from telethon.tl.types.messages import AllStickers
from telethon.tl.types import InputStickerSetShortName, Document, DocumentAttributeSticker
from telethon.tl.types.messages import StickerSet as StickerSetFull

from .lib import matrix, util


async def reupload_document(client: TelegramClient, document: Document) -> matrix.StickerInfo:
    print(f"Reuploading {document.id}", end="", flush=True)
    data = await client.download_media(document, file=bytes)
    print(".", end="", flush=True)
    data, width, height = util.convert_image(data)
    print(".", end="", flush=True)
    mxc = await matrix.upload(data, "image/png", f"{document.id}.png")
    print(".", flush=True)
    return util.make_sticker(mxc, width, height, len(data))


def add_meta(document: Document, info: matrix.StickerInfo, pack: StickerSetFull) -> None:
    for attr in document.attributes:
        if isinstance(attr, DocumentAttributeSticker):
            info["body"] = attr.alt
    info["net.maunium.telegram.sticker"] = {
        "id": str(document.id),
    }


async def reupload_pack(client: TelegramClient, pack: StickerSetFull, output_dir: str, roomid: str, statekey: str) -> None:
    if pack.set.animated:
        print("Animated stickerpacks are currently not supported")
        return

    pack_path = os.path.join(output_dir, f"{pack.set.short_name}.json")
    try:
        os.mkdir(os.path.dirname(pack_path))
    except FileExistsError:
        pass

    print(f"Reuploading {pack.set.title} with {pack.set.count} stickers "
          f"and writing output to {pack_path}")

    already_uploaded = {}
    try:
        with open(pack_path) as pack_file:
            existing_pack = json.load(pack_file)
            already_uploaded = {int(sticker["net.maunium.telegram.sticker"]["id"]): sticker
                                for sticker in existing_pack["images"].values()}
            print(f"Found {len(already_uploaded)} already reuploaded stickers")
    except FileNotFoundError:
        pass

    reuploaded_documents: Dict[int, matrix.StickerInfo] = {}
    for document in pack.documents:
        try:
            reuploaded_documents[document.id] = already_uploaded[document.id]
            print(f"Skipped reuploading {document.id}")
        except KeyError:
            reuploaded_documents[document.id] = await reupload_document(client, document)
        # Always ensure the body and telegram metadata is correct
        add_meta(document, reuploaded_documents[document.id], pack)

    dup_key: Set[str] = set()
    for sticker in pack.packs:
        if not sticker.emoticon:
            continue
        for document_id in sticker.documents:
            doc = reuploaded_documents[document_id]
            # If there was no sticker metadata, use the first emoji we find
            if doc["body"] == "":
                doc["body"] = sticker.emoticon
            key = sticker.emoticon
            while key in dup_key:
                key = key+sticker.emoticon
            doc["net.maunium.telegram.sticker"]["emoticon"] = key
            dup_key.add(key)

    data = json.dumps({
            "net.maunium.telegram.pack": {
                "short_name": pack.set.short_name,
                "hash": str(pack.set.hash),
                "id": f"tg-{pack.set.id}",
                "title": pack.set.title,
            },
            "pack": {
                "display_name": pack.set.title,
                "usage": ["sticker"]
            },
            "images": {s["net.maunium.telegram.sticker"]["emoticon"]: s for s in reuploaded_documents.values()},
        }, ensure_ascii=False)
    with open(pack_path, "w") as pack_file:
        pack_file.write(data)
    print(f"Saved {pack.set.title} as {pack.set.short_name}.json")

    if (roomid and statekey):
        print(f"Uploading pack into {roomid} with key {statekey}")
        resp = await matrix.insert_sticker_into_room(data, roomid, statekey)
        print(f"response: {resp}")

    util.add_to_index(os.path.basename(pack_path), output_dir)


pack_url_regex = re.compile(r"^(?:(?:https?://)?(?:t|telegram)\.(?:me|dog)/addstickers/)?"
                            r"([A-Za-z0-9-_]+)"
                            r"(?:\.json)?$")

parser = argparse.ArgumentParser()

parser.add_argument("--list", help="List your saved sticker packs", action="store_true")
parser.add_argument("--session", help="Telethon session file name", default="sticker-import")
parser.add_argument("--config",
                    help="Path to JSON file with Matrix homeserver and access_token",
                    type=str, default="config.json")
parser.add_argument("--output-dir", help="Directory to write packs to", default="web/packs/",
                    type=str)
parser.add_argument("--roomid",
                    help="Roomid to upload this pack to",
                    type=str, default="")
parser.add_argument("--statekey",
                    help="Statekey to use for this pack",
                    type=str, default="")
parser.add_argument("pack", help="Sticker pack URLs to import", action="append", nargs="*")


async def main(args: argparse.Namespace) -> None:
    await matrix.load_config(args.config)
    client = TelegramClient(args.session, 298751, "cb676d6bae20553c9996996a8f52b4d7")
    await client.start()

    if args.list:
        stickers: AllStickers = await client(GetAllStickersRequest(hash=0))
        index = 1
        width = len(str(stickers.sets))
        print("Your saved sticker packs:")
        for saved_pack in stickers.sets:
            print(f"{index:>{width}}. {saved_pack.title} "
                  f"(t.me/addstickers/{saved_pack.short_name})")
    elif args.pack[0]:
        input_packs = []
        for pack_url in args.pack[0]:
            match = pack_url_regex.match(pack_url)
            if not match:
                print(f"'{pack_url}' doesn't look like a sticker pack URL")
                return
            input_packs.append(InputStickerSetShortName(short_name=match.group(1)))
        for input_pack in input_packs:
            pack: StickerSetFull = await client(GetStickerSetRequest(input_pack))
            await reupload_pack(client, pack, args.output_dir, args.roomid, args.statekey)
    else:
        parser.print_help()

    await client.disconnect()


def cmd() -> None:
    asyncio.get_event_loop().run_until_complete(main(parser.parse_args()))


if __name__ == "__main__":
    cmd()
