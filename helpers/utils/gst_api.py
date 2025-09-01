import requests
from entity.models import Mastergstdetails
from Crypto.Cipher import AES
import base64
import json
import hashlib


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
    



def authenticate_ewaybill(gst_details):
    """
    Authenticate with the e-Way Bill API and retrieve required headers if successful.
    """
    url = "https://api.mastergst.com/ewaybillapi/v1.03/authenticate"

    headers = {
        "accept": "application/json",
        "ip_address": "10.178.787.78",
        "client_id": gst_details.client_id,
        "client_secret": gst_details.client_secret,
        "gstin": gst_details.gstin,
    }

    params = {
        "email": gst_details.email,
        "username": gst_details.username,
        "password": gst_details.password,
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        response_data = response.json()

        if response_data.get("status_cd") == "1":
            return response_data.get("header")  # You can extract needed fields from this
        else:
            return {
                "error": response_data.get("status_desc", "Authentication failed"),
                "details": response_data
            }

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

        print

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
    



import requests

def create_ewaybill(order, json_data):
    """
    Create an e-Way Bill using the MasterGST API.
    Expects `json_data` as a valid serialized JSON string.
    """
    try:
        # 1. Get GST details
        gst_details = Mastergstdetails.objects.first()
        if not gst_details:
            return {"error": "GST configuration not found."}

        # 2. Authenticate for e-Way Bill (not e-Invoice)
        auth_token = authenticate_ewaybill(gst_details)
        if isinstance(auth_token, dict) and auth_token.get("error"):
            return {"error": "Authentication failed", "details": auth_token}

        # 3. Prepare headers and URL
        url = "https://api.mastergst.com/ewaybillapi/v1.03/ewayapi/genewaybill"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "ip_address": "10.178.787.78",  # Static or make dynamic
            "client_id": gst_details.client_id,
            "client_secret": gst_details.client_secret,
            "gstin": gst_details.gstin,
            "username": gst_details.username,
            "auth-token": auth_token
        }
        params = {"email": gst_details.email}

        # 4. Call API
        response = requests.post(url, headers=headers, params=params, data=json_data)
        response_data = response.json()

        # 5. Handle success
        if response_data.get("status_cd") == "1" and "ewayBillNo" in response_data.get("data", {}):
            data = response_data["data"]
            order.ewaybill_no = data.get("ewayBillNo")
            order.ewaybill_date = data.get("ewayBillDate")
            order.valid_upto = data.get("validUpto")
            order.qr_code = data.get("qrCode")
            order.save()

        return response_data

    except Exception as e:
        return {"error": "Exception occurred during e-Way Bill generation", "details": str(e)}


    



def pad(text):
    """
    PKCS7 Padding
    """
    pad_len = 16 - len(text) % 16
    return text + chr(pad_len) * pad_len

def encrypt_payload(json_string, client_secret):
    """
    Encrypt payload using AES-256 ECB with SHA-256 derived key.
    """
    key = hashlib.sha256(client_secret.encode('utf-8')).digest()  # 32-byte key
    cipher = AES.new(key, AES.MODE_ECB)
    padded_data = pad(json_string)
    encrypted_bytes = cipher.encrypt(padded_data.encode('utf-8'))
    encrypted_base64 = base64.b64encode(encrypted_bytes).decode('utf-8')
    return encrypted_base64

    



def gst_ewaybill(order, json_data):


    print(json_data)
    """
    Generic E-Way Bill function for MasterGST.
    Pass pre-serialized JSON (`json_data`) as payload.
    """
    try:
        gst_details = Mastergstdetails.objects.first()
        if not gst_details:
            return {"error": "GST configuration not found."}

        # 1. Authenticate
        auth_token = authenticate_gst(gst_details)
        if isinstance(auth_token, dict) and auth_token.get("error"):
            return {"error": "Authentication failed", "details": auth_token}

        # 2. Encrypt Payload
        encrypted_text = encrypt_payload(json_data, gst_details.client_secret)
        final_payload = json.dumps({"data": encrypted_text})

        # 3. Prepare Headers & API Request
        url = "https://api.mastergst.com/einvoice/type/GENERATE_EWAYBILL/version/V1_03"
        headers = {
            "accept": "*/*",
            "Content-Type": "application/json",
            "ip_address": "49.43.101.20",
            "client_id": gst_details.client_id,
            "client_secret": gst_details.client_secret,
            "username": gst_details.username,
            "auth-token": auth_token,
            "gstin": gst_details.gstin
        }
        params = {"email": gst_details.email}


        print(final_payload)

        # 4. Call API
        response = requests.post(url, headers=headers, params=params, data=final_payload)
        response_data = response.json()

        # 5. Update Order if successful
        if response_data.get("status_cd") == "1" and "EwbNo" in response_data.get("data", {}):
            data = response_data["data"]
            order.ewaybill_no = data.get("EwbNo")
            order.ewaybill_date = data.get("EwbDt")
            order.valid_upto = data.get("ValidUpto")
            order.save()

        return response_data

    except Exception as e:
        return {"error": "Exception occurred during E-Way Bill generation", "details": str(e)}



def cancel_gst_invoice(irn, cancel_reason_code, cancel_remark):
    """
    Cancel E-Invoice via MasterGST API using IRN directly.
    
    :param irn: The IRN (Invoice Reference Number) to cancel
    :param cancel_reason_code: Cancellation Reason Code (as per MasterGST spec)
    :param cancel_remark: Cancellation Remarks
    :return: API Response dict
    """
    try:
        if not irn:
            return {"error": "IRN is required to cancel E-Invoice."}

        gst_details = Mastergstdetails.objects.first()
        if not gst_details:
            return {"error": "GST configuration not found."}

        # 1. Authenticate
        auth_token = authenticate_gst(gst_details)
        if isinstance(auth_token, dict) and auth_token.get("error"):
            return {"error": "Authentication failed", "details": auth_token}

        # 2. Prepare Headers & API Request
        url = "https://api.mastergst.com/einvoice/type/CANCEL/version/V1_03"
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

        payload = {
            "Irn": irn,
            "CnlRsn": str(cancel_reason_code),
            "CnlRem": cancel_remark
        }

        # 3. Call API
        response = requests.post(url, headers=headers, params=params, json=payload)
        response_data = response.json()

        return response_data

    except Exception as e:
        return {"error": "Exception occurred during e-invoice cancellation", "details": str(e)}

