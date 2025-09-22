# constants/stocktransconstant.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Optional

from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.models import Max

# import your models (keep your current names/paths)
# from app.models import (
#     staticacounts, staticacountsmapping,  # spelling kept as-is
#     tdsreturns, tdstype, tdsmain,
#     account, Entity
# )

from financial.models import account,staticacounts,staticacountsmapping
from invoice.models import tdsreturns,tdstype,tdsmain
from entity.models import Entity


# ---- Human-friendly code names (no more "6001" everywhere) ----
class StaticCode:
    CGST              = "6001"
    SGST              = "6002"
    IGST              = "6003"
    CESS              = "6004"
    ROUND_OFF_EXPENSE = "6011"
    ROUND_OFF_INCOME  = "6012"

    # Output tax reversals (if you use them)
    CGST_R            = "6005"
    SGST_R            = "6006"
    IGST_R            = "6007"

    CASH              = "4000"
    EXPENSES_MISC     = "8300"
    DISCOUNT          = "8400"
    BANK_CHARGES      = "8500"

    # TCS / TDS (liability/asset ledgers)
    TCS_206C1H_2      = "8050"  # your naming
    TCS_206C_2        = "8051"
    TDS_194Q_ASSET    = "8100"

    # Optional: receivable/payable variants (fallback to above if not mapped)
    TCS_206C1H_2_REC  = "9050"  # if you create separate receivable ledgers later
    TCS_206C_2_REC    = "9051"
    TDS_194Q_PAYABLE  = "9100"  # if you separate payable from receivable


@dataclass
class ConfigurationError(ImproperlyConfigured):
    message: str

    def __str__(self):
        return self.message


class stocktransconstant:
    """
    Fast, safe account resolver for a given entity:
      - Prefetches all mappings once (1 query) and caches them
      - Named methods for your existing callers (getcgst, getigst, ...)
      - Concurrency-safe TDS voucher number
    """

    # codes we commonly need; extend if you add more
    _DEFAULT_CODES = {
        StaticCode.CGST, StaticCode.SGST, StaticCode.IGST, StaticCode.CESS,
        StaticCode.CGST_R, StaticCode.SGST_R, StaticCode.IGST_R,
        StaticCode.ROUND_OFF_EXPENSE, StaticCode.ROUND_OFF_INCOME,
        StaticCode.CASH, StaticCode.EXPENSES_MISC,
        StaticCode.DISCOUNT, StaticCode.BANK_CHARGES,
        StaticCode.TCS_206C1H_2, StaticCode.TCS_206C_2,
        StaticCode.TDS_194Q_ASSET,
        # Optional receivable/payable splits
        StaticCode.TCS_206C1H_2_REC, StaticCode.TCS_206C_2_REC,
        StaticCode.TDS_194Q_PAYABLE,
    }

    def __init__(self, entity: Entity | int | None = None):
        self._entity: Optional[Entity] = None
        self._entity_id: Optional[int] = None
        self._cache: Dict[str, account] = {}  # code -> account

        if entity is not None:
            self.set_entity(entity)

        # memoize masters
        self._tdsreturn = None
        self._tdstype = None

    # ---------- entity binding ----------
    def set_entity(self, entity: Entity | int) -> "stocktransconstant":
        if isinstance(entity, int):
            self._entity_id = entity
        else:
            self._entity = entity
            self._entity_id = entity.id
        self._warm_cache()
        return self

    @property
    def entity_id(self) -> int:
        if self._entity_id is None:
            raise ConfigurationError("stocktransconstant: entity not set. Call set_entity(entity) first.")
        return self._entity_id

    # ---------- cache ----------
    def _warm_cache(self):
        """
        Prefetch all mappings for configured codes in ONE query.
        """
        if self._entity_id is None:
            return

        mappings = (staticacountsmapping.objects
                    .select_related("staticaccount", "account")
                    .filter(entity=self._entity_id,
                            staticaccount__code__in=self._DEFAULT_CODES))

        # fill from DB
        for m in mappings:
            self._cache[m.staticaccount.code] = m.account

        # keep keys for quick miss-detection (so we don't hit DB repeatedly)
        self._known_codes = set(self._DEFAULT_CODES)

    # ---------- fetchers ----------
    def _get(self, code: str, *, required: bool = True) -> Optional[account]:
        """
        Resolve a static code to an account, using cache; optionally require it.
        """
        # cached?
        if code in self._cache:
            acc = self._cache[code]
            if acc is None and required:
                raise ConfigurationError(f"Static account {code} mapped to NULL for entity {self.entity_id}")
            return acc

        # known but missing mapping: avoid repeated DB hits
        if hasattr(self, "_known_codes") and code in self._known_codes:
            if required:
                raise ConfigurationError(f"Static account {code} not mapped for entity {self.entity_id}")
            return None

        # unknown code (rare): fetch once and cache result
        try:
            sacc = staticacounts.objects.get(code=code)
            mapping = staticacountsmapping.objects.get(staticaccount=sacc, entity=self.entity_id)
            self._cache[code] = mapping.account
            return mapping.account
        except (staticacounts.DoesNotExist, staticacountsmapping.DoesNotExist):
            self._known_codes = getattr(self, "_known_codes", set())
            self._known_codes.add(code)
            if required:
                raise ConfigurationError(f"Static account {code} not mapped for entity {self.entity_id}")
            return None

    # keep your original public API (compat)
    def get_account_by_static_code(self, pentity, code):
        # allow calls with explicit pentity too (compat with your old signature)
        if pentity is not None and pentity != self._entity and (getattr(pentity, "id", pentity) != self._entity_id):
            self.set_entity(pentity)
        return self._get(code, required=False)

    # ---- Output taxes (sales) ----
    def getcgst(self, pentity=None): return self.get_account_by_static_code(pentity or self._entity_id, StaticCode.CGST)
    def getsgst(self, pentity=None): return self.get_account_by_static_code(pentity or self._entity_id, StaticCode.SGST)
    def getigst(self, pentity=None): return self.get_account_by_static_code(pentity or self._entity_id, StaticCode.IGST)
    def getcessid(self, pentity=None): return self.get_account_by_static_code(pentity or self._entity_id, StaticCode.CESS)

    # ---- Input taxes (purchase) – fallback to output if not mapped separately ----
    def get_input_cgst(self, pentity=None): return self.get_account_by_static_code(pentity or self._entity_id, StaticCode.CGST) or self.getcgst(pentity)
    def get_input_sgst(self, pentity=None): return self.get_account_by_static_code(pentity or self._entity_id, StaticCode.SGST) or self.getsgst(pentity)
    def get_input_igst(self, pentity=None): return self.get_account_by_static_code(pentity or self._entity_id, StaticCode.IGST) or self.getigst(pentity)
    def get_input_cess(self, pentity=None): return self.get_account_by_static_code(pentity or self._entity_id, StaticCode.CESS) or self.getcessid(pentity)

    # ---- TCS / TDS ----
    def gettcs206c1ch2id(self, pentity=None): return self.get_account_by_static_code(pentity or self._entity_id, StaticCode.TCS_206C1H_2)
    def gettcs206C2id(self, pentity=None):    return self.get_account_by_static_code(pentity or self._entity_id, StaticCode.TCS_206C_2)
    # receivable versions (purchase side), fallback to liabilities if not defined
    def gettcs206c1ch2_receivable(self, pentity=None): return self.get_account_by_static_code(pentity or self._entity_id, StaticCode.TCS_206C1H_2_REC) or self.gettcs206c1ch2id(pentity)
    def gettcs206C2_receivable(self, pentity=None):    return self.get_account_by_static_code(pentity or self._entity_id, StaticCode.TCS_206C_2_REC)    or self.gettcs206C2id(pentity)
    # TDS 194Q – receivable (sales) and payable (purchase)
    def gettds194q1id(self, pentity=None):        return self.get_account_by_static_code(pentity or self._entity_id, StaticCode.TDS_194Q_ASSET)
    def gettds194q1_payable(self, pentity=None):  return self.get_account_by_static_code(pentity or self._entity_id, StaticCode.TDS_194Q_PAYABLE) or self.gettds194q1id(pentity)

    # ---- Misc / cash / round-off ----
    def getexpensesid(self, pentity=None):        return self.get_account_by_static_code(pentity or self._entity_id, StaticCode.EXPENSES_MISC)
    def getcashid(self, pentity=None):            return self.get_account_by_static_code(pentity or self._entity_id, StaticCode.CASH)
    def getdiscount(self, pentity=None):          return self.get_account_by_static_code(pentity or self._entity_id, StaticCode.DISCOUNT)
    def getbankcharges(self, pentity=None):       return self.get_account_by_static_code(pentity or self._entity_id, StaticCode.BANK_CHARGES)
    def getroundoffincome(self, pentity=None):    return self.get_account_by_static_code(pentity or self._entity_id, StaticCode.ROUND_OFF_INCOME)
    def getroundoffexpnses(self, pentity=None):   return self.get_account_by_static_code(pentity or self._entity_id, StaticCode.ROUND_OFF_EXPENSE)

    # ---- Masters (cached) ----
    def gettdsreturnid(self):
        if self._tdsreturn is None:
            self._tdsreturn = tdsreturns.objects.get(tdsreturnname='26Q TDS')
        return self._tdsreturn

    def gettdstypeid(self):
        if self._tdstype is None:
            self._tdstype = tdstype.objects.get(tdssection='194Q')
        return self._tdstype

    # ---- Voucher sequence (concurrency-safe) ----
    def gettdsvbono(self, pentity=None) -> int:
        """
        Generate next TDS voucher no. Uses SELECT ... FOR UPDATE to serialize access.
        Works best inside a transaction.atomic() block.
        If you expect heavy concurrency, consider a dedicated Sequence model.
        """
        ent = pentity or self.entity_id
        with transaction.atomic():
            # Lock the rows for this entity to avoid race on max(voucherno)
            last = (tdsmain.objects
                    .select_for_update()
                    .filter(entityid=ent)
                    .order_by("-voucherno")
                    .first())
            return 1 if last is None else int(last.voucherno) + 1

    # ---- Convenience bundles used by your Poster ----
    def get_output_tax_accounts(self):
        return {
            "cgst": self.getcgst(),
            "sgst": self.getsgst(),
            "igst": self.getigst(),
            "cess": self.getcessid(),
        }

    def get_input_tax_accounts(self):
        return {
            "cgst": self.get_input_cgst(),
            "sgst": self.get_input_sgst(),
            "igst": self.get_input_igst(),
            "cess": self.get_input_cess(),
        }

    def get_roundoff_accounts(self):
        return (self.getroundoffincome(), self.getroundoffexpnses())
