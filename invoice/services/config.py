from invoice.models import PostingConfig
from invoice.stocktransconstant import stocktransconstant

class EffectivePostingConfig:
    def __init__(self, entity):
        self.entity = entity
        self.const = stocktransconstant()
        self.cfg = getattr(entity, "posting_config", None)

    # carrier & order
    def carrier(self, is_payment: bool) -> str:
        if not self.cfg:
            return PostingConfig.CARRIER_CB
        return self.cfg.adjustment_carrier_on_payment if is_payment else self.cfg.adjustment_carrier_on_receipt

    def order(self, is_payment: bool) -> str:
        if not self.cfg:
            return PostingConfig.ORDER_BETWEEN
        return self.cfg.presentation_order_on_payment if is_payment else self.cfg.presentation_order_on_receipt

    # per-component targets
    def targets(self, is_payment: bool) -> dict:
        if not self.cfg:
            return {"discount": PostingConfig.TARGET_CARRIER,
                    "bankcharges": PostingConfig.TARGET_CARRIER,
                    "tds": PostingConfig.TARGET_CARRIER}
        if is_payment:
            return {
                "discount":    self.cfg.discount_offset_target_on_payment,
                "bankcharges": self.cfg.bankcharges_offset_target_on_payment,
                "tds":         self.cfg.tds_offset_target_on_payment,
            }
        return {
            "discount":    self.cfg.discount_offset_target_on_receipt,
            "bankcharges": self.cfg.bankcharges_offset_target_on_receipt,
            "tds":         self.cfg.tds_offset_target_on_receipt,
        }

    # accounts (override → fallback to constants)
    def discount_account(self, is_payment: bool):
        if self.cfg:
            if is_payment and self.cfg.discount_account_payment_id:
                return self.cfg.discount_account_payment
            if (not is_payment) and self.cfg.discount_account_receipt_id:
                return self.cfg.discount_account_receipt
        return self.const.getdiscount(self.entity)

    def bank_charges_account(self):
        return (self.cfg and self.cfg.bank_charges_account) or self.const.getbankcharges(self.entity)

    def tds_receivable_account(self):
        return (self.cfg and self.cfg.tds_receivable_account) or self.const.gettds194q1id(self.entity)

    def tds_payable_account(self):
        return (self.cfg and self.cfg.tds_payable_account) or self.const.gettds194q1id(self.entity)
