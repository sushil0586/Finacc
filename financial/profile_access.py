from financial.models import account


def account_compliance_profile(acc: account):
    return getattr(acc, "compliance_profile", None)


def account_commercial_profile(acc: account):
    return getattr(acc, "commercial_profile", None)


def account_primary_address(acc: account):
    prefetched = getattr(acc, "prefetched_primary_addresses", None)
    if prefetched:
        return prefetched[0]
    addresses = getattr(acc, "addresses", None)
    if addresses is None:
        return None
    return addresses.filter(isprimary=True, isactive=True).first()


def account_primary_contact(acc: account):
    prefetched = getattr(acc, "prefetched_primary_contacts", None)
    if prefetched:
        return prefetched[0]
    contacts = getattr(acc, "contact_details", None)
    if contacts is None:
        return None
    return contacts.filter(isprimary=True).first()


def account_primary_bank_detail(acc: account):
    prefetched = getattr(acc, "prefetched_primary_bank_details", None)
    if prefetched:
        return prefetched[0]
    banks = getattr(acc, "bank_details", None)
    if banks is None:
        return None
    return banks.filter(isprimary=True, isactive=True).first()


def account_gstno(acc: account):
    return getattr(account_compliance_profile(acc), "gstno", None)


def account_pan(acc: account):
    return getattr(account_compliance_profile(acc), "pan", None)


def account_partytype(acc: account):
    return getattr(account_commercial_profile(acc), "partytype", None)


def account_creditlimit(acc: account):
    return getattr(account_commercial_profile(acc), "creditlimit", None)


def account_creditdays(acc: account):
    return getattr(account_commercial_profile(acc), "creditdays", None)


def account_currency(acc: account):
    return getattr(account_commercial_profile(acc), "currency", None)


def account_agent(acc: account):
    return getattr(account_commercial_profile(acc), "agent", None)


def account_approved(acc: account):
    return getattr(account_commercial_profile(acc), "approved", None)


def account_region_state(acc: account):
    address = account_primary_address(acc)
    if address and getattr(address, "state", None):
        return address.state
    return None


def account_region_state_id(acc: account):
    address = account_primary_address(acc)
    if address and getattr(address, "state_id", None):
        return address.state_id
    return None


def account_primary_email(acc: account):
    contact = account_primary_contact(acc)
    if contact and getattr(contact, "emailid", None):
        return contact.emailid
    return None


def account_primary_phone(acc: account):
    contact = account_primary_contact(acc)
    if contact and getattr(contact, "phoneno", None):
        return contact.phoneno
    return None


def account_primary_contact_person(acc: account):
    contact = account_primary_contact(acc)
    if contact and getattr(contact, "full_name", None):
        return contact.full_name
    return None


def account_primary_bank_name(acc: account):
    bank = account_primary_bank_detail(acc)
    if bank and getattr(bank, "bankname", None):
        return bank.bankname
    return None


def account_primary_bank_account(acc: account):
    bank = account_primary_bank_detail(acc)
    if bank and getattr(bank, "banKAcno", None):
        return bank.banKAcno
    return None
