from django.db import migrations


LEGACY_TABLES = [
    "inventory_barcodedetail",
    "inventory_billofmaterial",
    "inventory_bomitem",
    "inventory_gstrate",
    "inventory_gsttype",
    "inventory_hsnchaper",
    "inventory_hsncode",
    "inventory_product",
    "inventory_productcategory",
    "inventory_productionconsumption",
    "inventory_productionorder",
    "inventory_productionoutput",
    "inventory_qualitycheck",
    "inventory_ratecalculate",
    "inventory_stkcalculateby",
    "inventory_stkvaluationby",
    "inventory_typeofgoods",
    "inventory_unitofmeasurement",
    "invoice_accountentry",
    "invoice_addldocdtls",
    "invoice_closingstock",
    "invoice_debitcreditnote",
    "invoice_defaultvaluesbyentity",
    "invoice_doctype",
    "invoice_einvoicedetails",
    "invoice_entry",
    "invoice_ewbdetails",
    "invoice_ewbdtls",
    "invoice_expdtls",
    "invoice_goodstransaction",
    "invoice_gstorderservices",
    "invoice_gstorderservicesattachment",
    "invoice_gstorderservicesdetails",
    "invoice_historicalpurchaseorder",
    "invoice_historicalpurchaseorderdetails",
    "invoice_historicalsalesoderheader",
    "invoice_historicalsalesorderdetails",
    "invoice_historicalsalesquotationdetail",
    "invoice_historicalsalesquotationheader",
    "invoice_inventorymove",
    "invoice_invoicetype",
    "invoice_invoicetypes",
    "invoice_jobworkchalan",
    "invoice_jobworkchalandetails",
    "invoice_journal",
    "invoice_journaldetails",
    "invoice_journalline",
    "invoice_journallinehistory",
    "invoice_journalmain",
    "invoice_modeofpayment",
    "invoice_newpurchaseorder",
    "invoice_newpurchaseorderdetails",
    "invoice_paydtls",
    "invoice_paymentdetails",
    "invoice_paymentmodes",
    "invoice_paymentvoucher",
    "invoice_paymentvoucheradjustment",
    "invoice_paymentvoucherallocation",
    "invoice_postingconfig",
    "invoice_productiondetails",
    "invoice_productionmain",
    "invoice_purchaseorderattachment",
    "invoice_purchaseorderimport",
    "invoice_purchaseorderimportdetails",
    "invoice_purchaseothercharges",
    "invoice_purchaseotherimporattachment",
    "invoice_purchaseotherimportcharges",
    "invoice_purchasereturn",
    "invoice_purchasereturndetails",
    "invoice_purchasereturnothercharges",
    "invoice_purchasesettings",
    "invoice_purchasetaxtype",
    "invoice_receiptsettings",
    "invoice_receiptvoucher",
    "invoice_receiptvoucheradjustment",
    "invoice_receiptvoucherallocation",
    "invoice_refdtls",
    "invoice_saleothercharges",
    "invoice_salereturn",
    "invoice_salereturndetails",
    "invoice_salereturnothercharges",
    "invoice_salesinvoicesettings",
    "invoice_salesoder",
    "invoice_salesoderheader",
    "invoice_salesorderdetail",
    "invoice_salesorderdetails",
    "invoice_salesquotationdetail",
    "invoice_salesquotationheader",
    "invoice_stockdetails",
    "invoice_stockmain",
    "invoice_stocktransactions",
    "invoice_supplytype",
    "invoice_tdsmain",
    "invoice_tdsreturns",
    "invoice_tdstype",
    "invoice_transactions",
    "invoice_transportmode",
    "invoice_vehicaltype",
]


def drop_legacy_tables(apps, schema_editor):
    connection = schema_editor.connection
    existing = set(connection.introspection.table_names())
    vendor = connection.vendor

    for table_name in LEGACY_TABLES:
        if table_name not in existing:
            continue

        quoted = schema_editor.quote_name(table_name)
        if vendor == "postgresql":
            schema_editor.execute(f"DROP TABLE IF EXISTS {quoted} CASCADE")
        else:
            schema_editor.execute(f"DROP TABLE IF EXISTS {quoted}")


class Migration(migrations.Migration):
    dependencies = [
        ("financial", "0005_merge_20260312_0001"),
    ]

    operations = [
        migrations.RunPython(drop_legacy_tables, migrations.RunPython.noop),
    ]
