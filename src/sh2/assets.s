    .section .rodata
    .align 4
    .global _asset_bank
    .global _asset_bank_end
_asset_bank:
    .incbin "assets/bank.bin"
_asset_bank_end:

