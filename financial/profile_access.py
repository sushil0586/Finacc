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
    return getattr(acc, "state", None)


def account_region_state_id(acc: account):
    address = account_primary_address(acc)
    if address and getattr(address, "state_id", None):
        return address.state_id
    return getattr(acc, "state_id", None)
