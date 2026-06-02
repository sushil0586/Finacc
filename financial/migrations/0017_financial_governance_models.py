from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("entity", "0032_entitybankaccountv2_book_ledger"),
        ("Authentication", "0004_remove_submenu_mainmenu_remove_authotp_code_and_more"),
        ("financial", "0016_accountcomplianceprofile_msme_structured_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="FinancialMasterRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("template_code", models.CharField(blank=True, max_length=50, null=True)),
                ("party_type", models.CharField(blank=True, choices=[("Customer", "Customer"), ("Vendor", "Vendor"), ("Both", "Customer & Vendor"), ("Bank", "Bank"), ("Employee", "Employee"), ("Government", "Government"), ("Other", "Other")], max_length=20, null=True)),
                ("management_mode", models.CharField(choices=[("party_managed", "Party Managed"), ("ledger_only", "Ledger Only")], max_length=20)),
                ("auto_create_account", models.BooleanField(default=False)),
                ("allow_direct_ledger_edit", models.BooleanField(default=True)),
                ("priority", models.PositiveIntegerField(default=100)),
                ("account_type", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="financial_master_rules", to="financial.accounttype")),
                ("createdby", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to="Authentication.user")),
                ("credit_head", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="financial_master_credit_rules", to="financial.accounthead")),
                ("debit_head", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="financial_master_debit_rules", to="financial.accounthead")),
                ("entity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="financial_master_rules", to="entity.entity")),
                ("suggested_account_type", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="financial_master_rule_suggestions", to="financial.accounttype")),
                ("suggested_credit_head", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="financial_master_rule_credit_suggestions", to="financial.accounthead")),
                ("suggested_debit_head", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="financial_master_rule_debit_suggestions", to="financial.accounthead")),
            ],
            options={
                "ordering": ("created_at",),
            },
        ),
        migrations.CreateModel(
            name="FinancialCodeSeries",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("template_code", models.CharField(blank=True, max_length=50, null=True)),
                ("series_key", models.CharField(max_length=50)),
                ("label", models.CharField(max_length=100)),
                ("party_type", models.CharField(blank=True, choices=[("Customer", "Customer"), ("Vendor", "Vendor"), ("Both", "Customer & Vendor"), ("Bank", "Bank"), ("Employee", "Employee"), ("Government", "Government"), ("Other", "Other")], max_length=20, null=True)),
                ("range_start", models.PositiveIntegerField()),
                ("range_end", models.PositiveIntegerField()),
                ("next_code", models.PositiveIntegerField()),
                ("increment_step", models.PositiveIntegerField(default=1)),
                ("is_reserved_anchor", models.BooleanField(default=False)),
                ("priority", models.PositiveIntegerField(default=100)),
                ("account_type", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="financial_code_series", to="financial.accounttype")),
                ("createdby", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to="Authentication.user")),
                ("credit_head", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="financial_credit_code_series", to="financial.accounthead")),
                ("debit_head", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="financial_debit_code_series", to="financial.accounthead")),
                ("entity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="financial_code_series", to="entity.entity")),
            ],
            options={
                "ordering": ("created_at",),
            },
        ),
        migrations.CreateModel(
            name="FinancialCodeSeriesAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("allocated_code", models.PositiveIntegerField()),
                ("allocated_at", models.DateTimeField(auto_now_add=True)),
                ("allocation_reason", models.CharField(choices=[("create", "Create"), ("repair", "Repair"), ("migration", "Migration"), ("import", "Import")], default="create", max_length=20)),
                ("account", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="code_allocations", to="financial.account")),
                ("allocated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="financial_code_allocations", to="Authentication.user")),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="financial_code_series_audit", to="entity.entity")),
                ("ledger", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="code_allocations", to="financial.ledger")),
                ("series", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="audit_rows", to="financial.financialcodeseries")),
            ],
        ),
        migrations.AddConstraint(
            model_name="financialcodeseries",
            constraint=models.UniqueConstraint(fields=("entity", "series_key"), name="uq_fincode_ent_series_key"),
        ),
        migrations.AddIndex(
            model_name="financialmasterrule",
            index=models.Index(fields=["entity", "priority"], name="ix_finrule_ent_pri"),
        ),
        migrations.AddIndex(
            model_name="financialmasterrule",
            index=models.Index(fields=["template_code", "priority"], name="ix_finrule_tpl_pri"),
        ),
        migrations.AddIndex(
            model_name="financialmasterrule",
            index=models.Index(fields=["party_type", "priority"], name="ix_finrule_party_pri"),
        ),
        migrations.AddIndex(
            model_name="financialcodeseries",
            index=models.Index(fields=["entity", "priority"], name="ix_fincode_ent_pri"),
        ),
        migrations.AddIndex(
            model_name="financialcodeseries",
            index=models.Index(fields=["template_code", "priority"], name="ix_fincode_tpl_pri"),
        ),
        migrations.AddIndex(
            model_name="financialcodeseries",
            index=models.Index(fields=["party_type", "priority"], name="ix_fincode_party_pri"),
        ),
        migrations.AddIndex(
            model_name="financialcodeseriesaudit",
            index=models.Index(fields=["entity", "allocated_at"], name="ix_fincodeaudit_ent_at"),
        ),
        migrations.AddIndex(
            model_name="financialcodeseriesaudit",
            index=models.Index(fields=["series", "allocated_code"], name="ix_fincodeaudit_series_code"),
        ),
    ]
