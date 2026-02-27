def register_all_providers():
    from sales.services.providers.registry import ProviderRegistry
    from sales.services.providers.mastergst import MasterGSTProvider

    ProviderRegistry.register_einvoice(MasterGSTProvider())