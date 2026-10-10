    .section .assets,"a"
    .align 4
    .global _asset_bank
_asset_bank:
    .incbin "assets/bank-main.bin"
    .section .romextra,"a"
    .incbin "assets/bank-extra.bin"

