from django.db import migrations, models


SEED_ERRORS = [
    ("1004", "Header GSTIN is required", "", ""),
    ("1005", "Invalid Token", "Token expired or wrong GSTIN/User/Token in headers.", "Refresh auth token and send correct GSTIN/User/Token in request headers."),
    ("1006", "User Name is required", "", ""),
    ("1007", "Authentication failed. Pls. inform the helpdesk", "Wrong request payload formation.", "Prepare request payload as per API docs."),
    ("1008", "Invalid login credentials", "Wrong user id or password.", "Use correct user id and password."),
    ("1010", "Invalid Client-ID/Client-Secret", "Wrong client id or client secret.", "Use correct client_id and client_secret."),
    ("1011", "Client Id is required", "", ""),
    ("1012", "Client Secret is required", "", ""),
    ("1013", "Decryption of password failed", "Auth API could not decrypt password.", "Use correct environment public key and encryption method."),
    ("1014", "Inactive User", "GSTIN status inactive or not enabled for e-invoice.", "Verify GSTIN is active and enabled on e-invoice portal."),
    ("1015", "Invalid GSTIN for this user", "Token GSTIN differs from GSTIN sent in header.", "Send GSTIN mapped with the auth token."),
    ("1016", "Decryption of App Key failed", "Auth API could not decrypt app key.", "Use correct public key and encryption method."),
    ("1017", "Incorrect user id/User does not exists", "", "Send correct user id."),
    ("1018", "Client Id is not mapped to this user", "", "Use user id mapped to the given client id."),
    ("1019", "Incorrect Password", "", "Use correct password."),
    ("2230", "This IRN cannot be cancelled because e-way bill has been generated.", "IRN cancellation attempted before EWB cancellation.", "Cancel EWB first, then cancel IRN."),
    ("2240", "GST rate of tax is incorrect or not as notified", "Item GST rate is invalid for IRN schema/master.", "Use correct notified GST slab for the item/HSN and regenerate IRN."),
    ("3001", "Requested data is not available", "", ""),
    ("3002", "Invalid login credentials", "", ""),
    ("3003", "Password policy violation", "Password is too weak.", "Use upper+lower+number+special character password."),
    ("3004", "This username is already registered. Please choose a different username.", "", ""),
    ("3005", "Requested data is not found", "", ""),
    ("3006", "Invalid Mobile Number", "", "Provide correct mobile number; sync from GST portal if changed."),
    ("3007", "You have exceeded the limit of creating sub-users", "", ""),
    ("3008", "Sub user exists for this user id", "", ""),
    ("3009", "Please provide required parameter or payload", "", ""),
    ("3010", "The suffix login id should contain 4 or lesser than 4 characters", "", ""),
    ("3011", "Data not Found", "", ""),
    ("3012", "Mobile No. is blank for this GSTIN", "", "Update mobile on GST common portal and retry."),
    ("3013", "Your registration under GST has been cancelled", "", ""),
    ("3014", "Gstin Not Allowed", "", ""),
    ("3015", "Sorry, your GSTIN is deregistered in GST Common Portal", "", "Verify GSTIN status and contact helpdesk if active on portal."),
    ("3016", "Your registration under GST is inactive", "", ""),
    ("3017", "Provisional ID not activated", "", ""),
    ("3019", "subuser details are not saved please try again", "", ""),
    ("3020", "Internal Server Error pls try after sometime", "", "Retry later."),
    ("3021", "There are no subusers for this gstin", "", ""),
    ("3022", "The Given Details Already Exists", "", ""),
    ("3023", "The New PassWord And Old PassWord Cannot Be Same", "", ""),
    ("3024", "Change of password unsuccessful", "", ""),
    ("3025", "Already This Account Has Been Freezed", "", ""),
    ("3027", "You are already registered", "", "Use forgot username/password options if needed."),
    ("3029", "GSTIN is inactive or cancelled", "GSTIN status not active.", "Sync GSTIN from GST common portal and retry after activation."),
    ("3030", "Invalid GSTIN", "", "Provide correct GSTIN."),
    ("3031", "Invalid User Name", "", ""),
    ("3032", "Enrolled Transporter cannot login to e-Invoice Portal", "", ""),
    ("3033", "Your account has been Freezed as GSTIN is inactive", "", ""),
    ("3034", "Your account has been cancelled as GSTIN is inactive", "", ""),
    ("3035", "Your account has been suspended as GSTIN is inactive", "", ""),
    ("3036", "Your account has been inactive", "", ""),
    ("3037", "CommonEnrolled Transporter not allowed this site", "", ""),
    ("3042", "Invalid From Pincode or To Pincode", "PIN code validation failed.", "Pass correct PIN. Verify from master codes."),
    ("3043", "Something went wrong, please try again after sometime", "", "Retry later; if persistent share full payload with helpdesk."),
    ("3044", "This registration only for tax payers not GSP", "", ""),
    ("3045", "Sorry you are not registered, Please use the registration option.", "", ""),
    ("3046", "Sorry you are not enabled for e-Invoicing System on Production.", "", ""),
    ("3052", "Transporter Id is cancelled or invalid", "", ""),
    ("3053", "Unauthorised access", "", ""),
    ("3058", "Data not Saved", "", ""),
    ("3059", "Client-Id for this PAN is not generated check your IP-Whitelisting status.", "", ""),
    ("3060", "Please wait for officer approval", "", ""),
    ("3061", "Your Request has been rejected, please register again", "", ""),
    ("3062", "Already Registered", "", ""),
    ("3063", "You are already enabled for e-invoicing", "", ""),
    ("3064", "Sorry, This GSTIN is deregistered", "", ""),
    ("3065", "You are not allowed to use this feature.", "", ""),
    ("3066", "There is no pin codes availables for this state.", "", ""),
    ("3067", "Client secret unsuccessful, please check the existing client secret.", "", ""),
    ("3068", "There is no Api user.", "", ""),
    ("3069", "Sorry, you have not directly integrated with E-invoice API.", "", ""),
    ("3070", "Sorry, you have not registered.", "", ""),
    ("3071", "Sorry, you have already linked this Gstin to your Client Id.", "", ""),
    ("3072", "Sorry, Your GSTIN not enabled by the Direct Integrator.", "", ""),
    ("3073", "You are already registered.", "", ""),
]


def seed_error_catalog(apps, schema_editor):
    Model = apps.get_model("sales", "SalesComplianceErrorCode")
    for idx, (code, message, reason, resolution) in enumerate(SEED_ERRORS, start=1):
        Model.objects.update_or_create(
            code=code,
            defaults={
                "message": message,
                "reason": reason,
                "resolution": resolution,
                "source": "NIC_MASTERGST",
                "is_active": True,
                "sort_order": idx,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0019_compliance_ops_and_controls"),
    ]

    operations = [
        migrations.CreateModel(
            name="SalesComplianceErrorCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(db_index=True, max_length=16, unique=True)),
                ("message", models.CharField(max_length=255)),
                ("reason", models.TextField(blank=True, default="")),
                ("resolution", models.TextField(blank=True, default="")),
                ("source", models.CharField(db_index=True, default="NIC_MASTERGST", max_length=30)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("sort_order", models.PositiveIntegerField(default=1000)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "sales_compliance_error_code",
                "ordering": ["sort_order", "code"],
            },
        ),
        migrations.AddIndex(
            model_name="salescomplianceerrorcode",
            index=models.Index(fields=["source", "is_active"], name="idx_sales_cmp_err_src_active"),
        ),
        migrations.AddIndex(
            model_name="salescomplianceerrorcode",
            index=models.Index(fields=["sort_order", "code"], name="idx_sales_cmp_err_sort"),
        ),
        migrations.RunPython(seed_error_catalog, migrations.RunPython.noop),
    ]
