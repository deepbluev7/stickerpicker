# Sticker pack converter
A simple converter of TG sticker packs to [MSC2545](https://github.com/matrix-org/matrix-doc/pull/2545) sticker packs.

Based on the maunium sticker picker: https://github.com/maunium/stickerpicker/

## Instructions

You can use the instructions from the maunium stickerpicker to import sticker packs: https://github.com/maunium/stickerpicker/wiki/Creating-packs#importing-packs-from-telegram

Then just upload the json manually as an image pack account/state event.

Alternatively you can use the `--roomid` and `--statekey` arguments to automatically create the pack as a state event.

## Limitations

Telegram stickerpacks don't have easily searchable descriptions, so the shortcode for each sticker will be just an emoji.
