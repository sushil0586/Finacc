import requests
from entity.models import Mastergstdetails


def authenticate_gst(gst_details):
    """
    Authenticate with the GST API and retrieve the AuthToken.
    """
    url = "https://api.mastergst.com/einvoice/authenticate"

    headers = {
        "accept": "*/*",
        "username": gst_details.username,
        "password": gst_details.password,
        "ip_address": "49.43.101.20",
        "client_id": gst_details.client_id,
        "client_secret": gst_details.client_secret,
        "gstin": gst_details.gstin,
    }

    params = {"email": gst_details.email}

    try:
        response = requests.get(url, headers=headers, params=params)
        response_data = response.json()

        if response_data.get("status_cd") == "Sucess":
            return response_data["data"]["AuthToken"]
        else:
            return {"error": response_data.get("status_desc", "Authentication failed")}
    except requests.RequestException as e:
        return {"error": str(e)}

def get_gst_details(entitygst):
    """
    Fetch GSTN details using the authentication token.
    """
    # Fetch the stored credentials only once
    gst_details = Mastergstdetails.objects.first()
    if not gst_details:
        return {"error": "No GST details found in the database."}

    # Authenticate and get AuthToken
    auth_token = authenticate_gst(gst_details)

    print(auth_token)
    if isinstance(auth_token, dict) and "error" in auth_token:
        return auth_token  # Return error if authentication fails

    url = "https://api.mastergst.com//einvoice/type/GSTNDETAILS/version/V1_03"

    headers = {
        "accept": "*/*",
        "ip_address": "49.43.101.20",
        "client_id": gst_details.client_id,
        "client_secret": gst_details.client_secret,
        "username": gst_details.username,
        "auth-token": auth_token,  # Use the obtained AuthToken
        "gstin": gst_details.gstin,
    }

    params = {
        "param1": entitygst,
        "email": gst_details.email,
    }

    try:


        print(headers)
        print(params)


        response = requests.get(url, headers=headers, params=params)
        response_data = response.json()

        print(response_data)

        if response_data.get("status_cd") == "1":
            return response_data["data"]
        else:
            return {"error": response_data.get("status_desc", "Request failed")}
    except requests.RequestException as e:
        return {"error": str(e)}
    

def gstinvoice(order, json_data):
    """
    Generic GST invoice function that can be used for Invoice, Debit Note, Credit Note.
    Pass pre-serialized JSON (`json_data`) to keep it flexible.
    """
    try:
        gst_details = Mastergstdetails.objects.first()
        if not gst_details:
            return {"error": "GST configuration not found."}

        # 1. Authenticate
        auth_token = authenticate_gst(gst_details)
        if isinstance(auth_token, dict) and auth_token.get("error"):
            return {"error": "Authentication failed", "details": auth_token}

        # 2. Prepare Headers & API Request
        url = "https://api.mastergst.com/einvoice/type/GENERATE/version/V1_03"
        headers = {
            "accept": "*/*",
            "Content-Type": "application/json",
            "ip_address": "49.43.101.20",  # Replace with dynamic if needed
            "client_id": gst_details.client_id,
            "client_secret": gst_details.client_secret,
            "username": gst_details.username,
            "auth-token": auth_token,
            "gstin": gst_details.gstin
        }
        params = {"email": gst_details.email}

        # 3. Call API
        response = requests.post(url, headers=headers, params=params, data=json_data)
        response_data = response.json()

        # 4. Update Order if successful
        if response_data.get("status_cd") == "1" and "Irn" in response_data.get("data", {}):
            data = response_data["data"]
            order.irn = data.get("Irn")
            order.ackno = data.get("AckNo")
            order.ackdt = data.get("AckDt")
            order.signed_invoice = data.get("SignedInvoice")
            order.qr_code = data.get("SignedQRCode")
            order.save()

        return response_data

    except Exception as e:
        return {"error": "Exception occurred during e-invoice generation", "details": str(e)}