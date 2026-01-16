from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget

from entity.models import Entity
from Authentication.models import User
from geography.models import Country, State, District, City

from .models import (
    accounttype,
    accountHead,
    account,
    ShippingDetails,
    ContactDetails,
    staticacounts,
    staticacountsmapping,
)


# -----------------------------
# Helpers (optional safety)
# -----------------------------
def _blank_to_none(v):
    return None if v is None or str(v).strip() == "" else v


# -----------------------------
# accounttype
# Natural key: (entity, accounttypecode)
# -----------------------------
class AccountTypeResource(resources.ModelResource):
    entity = fields.Field(
        column_name="entity",
        attribute="entity",
        widget=ForeignKeyWidget(Entity, "entityname"),
    )
    createdby = fields.Field(
        column_name="createdby",
        attribute="createdby",
        widget=ForeignKeyWidget(User, "username"),  # adjust if you use email
    )

    class Meta:
        model = accounttype
        # IMPORTANT: do not use 'id' for cross-env
        import_id_fields = ("entity", "accounttypecode")
        fields = ("entity", "accounttypename", "accounttypecode", "balanceType", "createdby")
        skip_unchanged = True
        report_skipped = True

    def before_import_row(self, row, **kwargs):
        row["entity"] = _blank_to_none(row.get("entity"))
        row["createdby"] = _blank_to_none(row.get("createdby"))


# -----------------------------
# accountHead
# Natural key: (entity, code)
# -----------------------------
class AccountHeadResource(resources.ModelResource):
    entity = fields.Field(
        column_name="entity",
        attribute="entity",
        widget=ForeignKeyWidget(Entity, "entityname"),
    )
    accounttype = fields.Field(
        column_name="accounttypecode",
        attribute="accounttype",
        widget=ForeignKeyWidget(accounttype, "accounttypecode"),  # NOTE: see comment below
    )
    createdby = fields.Field(
        column_name="createdby",
        attribute="createdby",
        widget=ForeignKeyWidget(User, "username"),
    )
    accountheadsr = fields.Field(
        column_name="parent_code",
        attribute="accountheadsr",
        widget=ForeignKeyWidget(accountHead, "code"),
    )

    class Meta:
        model = accountHead
        import_id_fields = ("entity", "code")
        # Export accounttype as code column to keep portability
        fields = (
            "entity",
            "name",
            "code",
            "balanceType",
            "drcreffect",
            "description",
            "detailsingroup",
            "canbedeleted",
            "createdby",
            "accounttypecode",
            "parent_code",
        )
        skip_unchanged = True
        report_skipped = True

    def dehydrate_accounttypecode(self, obj):
        # export accounttype as accounttypecode (stable)
        return obj.accounttype.accounttypecode if obj.accounttype else ""

    def dehydrate_parent_code(self, obj):
        return obj.accountheadsr.code if obj.accountheadsr else ""

    def before_import_row(self, row, **kwargs):
        row["entity"] = _blank_to_none(row.get("entity"))
        row["createdby"] = _blank_to_none(row.get("createdby"))
        # allow blanks
        row["accounttypecode"] = _blank_to_none(row.get("accounttypecode"))
        row["parent_code"] = _blank_to_none(row.get("parent_code"))


"""
IMPORTANT NOTE about accounttype FK:
AccountHead.accounttype points to accounttype which is entity-scoped.
ForeignKeyWidget(accounttype, "accounttypecode") will match the FIRST accounttype with that code across all entities.
If accounttypecode is unique per entity, the safe approach is a custom widget that resolves by (entity, accounttypecode).
If you want that stricter version, tell me your rule for accounttypecode (global unique OR per entity), and I’ll paste the custom widget.
For now, this will work only if accounttypecode is globally unique OR you have same code mapping across entities.
"""


# -----------------------------
# account
# Natural key: (entity, accountcode) OR (entity, gstno) if you prefer
# -----------------------------
class AccountResource(resources.ModelResource):
    entity = fields.Field(
        column_name="entity",
        attribute="entity",
        widget=ForeignKeyWidget(Entity, "entityname"),
    )
    createdby = fields.Field(
        column_name="createdby",
        attribute="createdby",
        widget=ForeignKeyWidget(User, "username"),
    )

    accounthead = fields.Field(
        column_name="accounthead_code",
        attribute="accounthead",
        widget=ForeignKeyWidget(accountHead, "code"),
    )
    creditaccounthead = fields.Field(
        column_name="creditaccounthead_code",
        attribute="creditaccounthead",
        widget=ForeignKeyWidget(accountHead, "code"),
    )

    country = fields.Field(
        column_name="country",
        attribute="country",
        widget=ForeignKeyWidget(Country, "name"),
    )
    state = fields.Field(
        column_name="state",
        attribute="state",
        widget=ForeignKeyWidget(State, "name"),
    )
    district = fields.Field(
        column_name="district",
        attribute="district",
        widget=ForeignKeyWidget(District, "name"),
    )
    city = fields.Field(
        column_name="city",
        attribute="city",
        widget=ForeignKeyWidget(City, "name"),
    )

    class Meta:
        model = account
        # Choose your natural key:
        # If accountcode is stable per entity, use (entity, accountcode)
        import_id_fields = ("entity", "accountcode")
        fields = (
            "entity",
            "accountcode",
            "accountname",
            "gstno",
            "pan",
            "emailid",
            "contactno",
            "openingbdr",
            "openingbcr",
            "accounthead_code",
            "creditaccounthead_code",
            "country",
            "state",
            "district",
            "city",
            "createdby",
        )
        skip_unchanged = True
        report_skipped = True

    def dehydrate_accounthead_code(self, obj):
        return obj.accounthead.code if obj.accounthead else ""

    def dehydrate_creditaccounthead_code(self, obj):
        return obj.creditaccounthead.code if obj.creditaccounthead else ""

    def before_import_row(self, row, **kwargs):
        row["entity"] = _blank_to_none(row.get("entity"))
        row["createdby"] = _blank_to_none(row.get("createdby"))
        row["accounthead_code"] = _blank_to_none(row.get("accounthead_code"))
        row["creditaccounthead_code"] = _blank_to_none(row.get("creditaccounthead_code"))
        # allow location blanks
        for k in ("country", "state", "district", "city"):
            row[k] = _blank_to_none(row.get(k))


# -----------------------------
# staticacounts
# Natural key: (entity, code)
# -----------------------------
class StaticAccountsResource(resources.ModelResource):
    entity = fields.Field(
        column_name="entity",
        attribute="entity",
        widget=ForeignKeyWidget(Entity, "entityname"),
    )
    createdby = fields.Field(
        column_name="createdby",
        attribute="createdby",
        widget=ForeignKeyWidget(User, "username"),
    )

    class Meta:
        model = staticacounts
        import_id_fields = ("entity", "code")
        fields = ("entity", "code", "staticaccount", "createdby")
        skip_unchanged = True
        report_skipped = True

    def before_import_row(self, row, **kwargs):
        row["entity"] = _blank_to_none(row.get("entity"))
        row["createdby"] = _blank_to_none(row.get("createdby"))


# -----------------------------
# staticacountsmapping
# Natural key: (entity, staticacounts.code, account.accountcode)
# -----------------------------
class StaticAccountsMappingResource(resources.ModelResource):
    entity = fields.Field(
        column_name="entity",
        attribute="entity",
        widget=ForeignKeyWidget(Entity, "entityname"),
    )
    staticaccount = fields.Field(
        column_name="static_code",
        attribute="staticaccount",
        widget=ForeignKeyWidget(staticacounts, "code"),
    )
    account = fields.Field(
        column_name="accountcode",
        attribute="account",
        widget=ForeignKeyWidget(account, "accountcode"),
    )
    createdby = fields.Field(
        column_name="createdby",
        attribute="createdby",
        widget=ForeignKeyWidget(User, "username"),
    )

    class Meta:
        model = staticacountsmapping
        import_id_fields = ("entity", "static_code", "accountcode")
        fields = ("entity", "static_code", "accountcode", "createdby")
        skip_unchanged = True
        report_skipped = True

    def dehydrate_static_code(self, obj):
        return obj.staticaccount.code if obj.staticaccount else ""

    def dehydrate_accountcode(self, obj):
        return obj.account.accountcode if obj.account else ""

    def before_import_row(self, row, **kwargs):
        row["entity"] = _blank_to_none(row.get("entity"))
        row["createdby"] = _blank_to_none(row.get("createdby"))
        row["static_code"] = _blank_to_none(row.get("static_code"))
        row["accountcode"] = _blank_to_none(row.get("accountcode"))
