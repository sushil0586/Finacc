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