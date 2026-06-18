def register_all_providers():
    from sales.services.providers.registry import ProviderRegistry
    from sales.services.providers.mastergst import MasterGSTProvider
    from sales.services.providers.whitebooks import WhitebooksProvider

    mastergst = MasterGSTProvider()
    whitebooks = WhitebooksProvider()

    ProviderRegistry.register_einvoice(mastergst)
    ProviderRegistry.register_einvoice(whitebooks)
    ProviderRegistry.register_eway(mastergst)
    ProviderRegistry.register_eway(whitebooks)
