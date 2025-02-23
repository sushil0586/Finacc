from django.http import request
from django.shortcuts import render

from rest_framework.generics import CreateAPIView,ListAPIView,ListCreateAPIView,RetrieveUpdateDestroyAPIView,GenericAPIView
from entity.models import Entity,entity_details,unitType,entityfinancialyear,Constitution,subentity,Rolepriv,Role,Userrole,Mastergstdetails,GstAccountsdetails
from entity.serializers import entityDetailsSerializer,unitTypeSerializer,entityAddSerializer,EntityFinancialYearSerializer,entityfinancialyearListSerializer,ConstitutionSerializer,subentitySerializer,subentitySerializerbyentity,roleSerializer,RoleMainSerializer,userbyentitySerializer,useroleentitySerializer,EntityFinancialYearSerializerlist
from rest_framework import permissions
from django_filters.rest_framework import DjangoFilterBackend
from Authentication.models import User
from django_pandas.io import read_frame
import numpy as np
import pandas as pd
from rest_framework.response import Response
from django.db import transaction
import requests,json
from django.db.models import Count
from geography.models import Country,State,District,City
from rest_framework import response,status,permissions
from helpers.utils.gst_api import get_gst_details



class generateeinvoice:

    def __init__(self,mastergst):
        self.mastergst = mastergst
        self.ipaddress = '10.105.87.909'
        self.username = self.mastergst.username
        self.headers = json.dumps({ 
                              'Content-Type': 'application/json',
                              'username':self.username,
                              'password':self.mastergst.password,
                              'ip_address': self.ipaddress,
                              'client_id': self.mastergst.client_id,
                              'client_secret': self.mastergst.client_secret,
                              'gstin': self.mastergst.gstin}, indent=4)
        
     
        self.headers = json.loads(self.headers)


    def get_gst_auth_token(self):
        """
        Fetch credentials from the database and authenticate with the GST API.
        """
        # Fetch the first or only record in the database
        gst_details = Mastergstdetails.objects.first()
        
        if not gst_details:
            return {"error": "No GST details found in the database."}

        url = "https://api.mastergst.com/einvoice/authenticate"

        headers = {
            "accept": "*/*",
            "username": gst_details.username,
            "password": gst_details.password,
            "ip_address": "49.43.101.20",  # You may want to store this in DB as well
            "client_id": gst_details.client_id,
            "client_secret": gst_details.client_secret,
            "gstin": gst_details.gstin,
        }

        params = {"email": "sushiljyotibansal@gmail.com"}

        try:
            response = requests.get(url, headers=headers, params=params)
            response_data = response.json()

            if response_data.get("status_cd") == "Sucess":
                return response_data["data"]["AuthToken"]
            else:
                return {"error": response_data.get("status_desc", "Authentication failed")}
        except requests.RequestException as e:
            return {"error": str(e)}

           


    def getauthentication(self):
        BASE_URL = 'https://api.mastergst.com/einvoice/authenticate'
        response = requests.get(f"{BASE_URL}?email=sushiljyotibansal@gmail.com", headers= self.headers)
        return response
    
    def getheaderdetails(self,authtoken):
        
        self.headers["auth-token"] = authtoken
        return self.headers
    

    

    def getgstdetails(self,gstaccount,authtoken,useremail):




       # "https://api.mastergst.com/einvoice/type/GSTNDETAILS/version/V1_03?param1=29AABCT1332L000&email=aditi.gupta1789%40gmail.com"



        BASE_URL = 'https://api.mastergst.com/einvoice/type/GSTNDETAILS/version/V1_03'

        self.headers["auth-token"] = authtoken



    
        

        #print(f"{BASE_URL}?email=aditi.gupta1789@gmail.com")

        response = requests.get(f"{BASE_URL}?param1={gstaccount}&email={useremail}", headers= self.headers)

        print(response)


        return response
    
   




class roleApiView(ListCreateAPIView):

    serializer_class = roleSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']

    # def perform_create(self, serializer):
    #     return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        return Role.objects.filter()







class entityAddApiView(ListCreateAPIView):

    serializer_class = entityAddSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']
    @transaction.atomic
    def perform_create(self, serializer):
        return serializer.save(user = [self.request.user])
    
    def get_queryset(self):
        return Entity.objects.filter(user = self.request.user)
    

class userAddApiView(CreateAPIView):

    def post(self,request):
        email = request.data.get('email',None)
        password = request.data.get('password',None)
        first_name = request.data.get('first_name',None)
        last_name = request.data.get('last_name',None)
        username = request.data.get('username',None)
        entityid = request.data.get('entityid',None)
        roleid = request.data.get('roleid',None)


        with transaction.atomic():
            userid = User.objects.create(first_name = first_name,last_name=last_name,username= username,password = password,email = email)
            roleid = Role.objects.get(entity = entityid,id = roleid)
            entity = Entity.objects.get(id = entityid)
            Userrole.objects.create(entity =entity,role =roleid,user=userid)
            stk = Userrole.objects.filter(entity = entity).values('user__first_name','user__last_name','user__email','user__username','user__password','role__rolename','role__id')
            df = read_frame(stk)
            df.rename(columns = {'user__first_name':'first_name','user__last_name':'last_name','user__email':'email','user__username':'username','user__password':'password','role__rolename':'rolename','role__id':'roleid'}, inplace = True)
            return Response(df.T.to_dict().values())


        

        


        





class userroleApiView(ListCreateAPIView):

    serializer_class = useroleentitySerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def perform_create(self, serializer):
        return serializer.save()
    
    def get_queryset(self):
        return Userrole.objects.filter()






class userroleupdatedel(RetrieveUpdateDestroyAPIView):

    serializer_class = useroleentitySerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        return Userrole.objects.filter()



class entityDetailsApiView(ListCreateAPIView):

    serializer_class = entityDetailsSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['style']

    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        return entity_details.objects.filter(createdby = self.request.user)


class unitTypeApiView(ListCreateAPIView):

    serializer_class = unitTypeSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']

    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        return unitType.objects.filter()
    


class ConstitutionApiView(ListAPIView):

    serializer_class = ConstitutionSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']

    # def perform_create(self, serializer):
    #     return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        return Constitution.objects.filter()

# class entityUserApiView(ListCreateAPIView):

#     serializer_class = entityUserSerializer
#     permission_classes = (permissions.IsAuthenticated,)

#     filter_backends = [DjangoFilterBackend]
#     filterset_fields = ['id','entity',]


    

#     def perform_create(self, serializer):
#         return serializer.save(createdby = self.request.user)
    
#     def get_queryset(self):

#        # entity = entity_user.objects.filter(user = self.request.user).order_by('entity')[0]

#     #print(entity)

#        # entity = self.request.query_params.get('entity')
#         return entity_user.objects.filter()




# # class entityUseraddApiView(ListCreateAPIView):

# #     serializer_class = entityUserAddSerializer
# #     permission_classes = (permissions.IsAuthenticated,)

# #     filter_backends = [DjangoFilterBackend]
# #     filterset_fields = ['id','entity',]


    

#     def perform_create(self, serializer):
#         return serializer.save(createdby = self.request.user)
    
#     def get_queryset(self):

#        # entity = entity_user.objects.filter(user = self.request.user).order_by('entity')[0]

#     #print(entity)

#        # entity = self.request.query_params.get('entity')
#         return entity_user.objects.filter()



# class AuthApiView(ListAPIView):

#     permission_classes = (permissions.IsAuthenticated,)

#     serializer_class = Userserializer
#     permission_classes = (permissions.IsAuthenticated,)

#     def get_queryset(self):
#         return User.objects.filter(email = self.request.user)
    

class EntityFinancialYearApiView(ListCreateAPIView):
    serializer_class = EntityFinancialYearSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def perform_create(self, serializer):
        return serializer.save(createdby=self.request.user)

    def get_queryset(self):
        queryset = entityfinancialyear.objects.filter(isactive=True)

        entity = self.request.query_params.get('entity')
        financialyearid = self.request.query_params.get('financialyearid')

        if entity:
            queryset = queryset.filter(entity=entity)

        return queryset.order_by('-isactive')

    def get_serializer_context(self):
        """Pass financialyearid to the serializer for additional data lookup"""
        return {
            **super().get_serializer_context(),
            'financialyearid': self.request.query_params.get('financialyearid')
        }
    

class subentityApiView(ListCreateAPIView):

    serializer_class = subentitySerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def perform_create(self, serializer):
        return serializer.save()
    
    def get_queryset(self):
        return subentity.objects.filter()
    
class rolenewApiView(ListCreateAPIView):

    serializer_class = RoleMainSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def perform_create(self, serializer):
        return serializer.save()
    
    def get_queryset(self):
        return Role.objects.filter()
    

class subentitybyentityApiView(ListCreateAPIView):

    serializer_class = subentitySerializerbyentity
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def perform_create(self, serializer):
        return serializer.save()
    
    def get_queryset(self):
        return subentity.objects.filter()
    

class subentityupdatedelview(RetrieveUpdateDestroyAPIView):

    serializer_class = subentitySerializer
    
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
      #  entity = self.request.query_params.get('entity')
        return subentity.objects.filter()
    

class rolenewupdatedelview(RetrieveUpdateDestroyAPIView):

    serializer_class = RoleMainSerializer
    
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
      #  entity = self.request.query_params.get('entity')
        return Role.objects.filter()
    





        

    



class entityfinancialyeaListView(ListAPIView):

    serializer_class = entityfinancialyearListSerializer
    permission_classes = (permissions.IsAuthenticated,)


    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    
    
    def get_queryset(self):
        return entityfinancialyear.objects.filter().order_by('-isactive')
    



# class entityupdatedel(RetrieveUpdateDestroyAPIView):

#     serializer_class = entitySerializer
#     permission_classes = (permissions.IsAuthenticated,)
#     lookup_field = "id"

#     def get_queryset(self):
#         return entity.objects.filter()
    


class roledetails(ListAPIView):

   
    permission_classes = (permissions.IsAuthenticated,)

      
    def get(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        entity1 = self.request.query_params.get('entity')
        role1 = self.request.query_params.get('role')
        stk = Role.objects.prefetch_related('submenudetails').filter(entity = entity1,id = role1).values('submenudetails__submenu__id','id','rolename','roledesc','rolelevel')

        df = read_frame(stk)
        df.rename(columns = {'id':'roleid','rolename':'rolename','roledesc':'roledesc','rolelevel':'rolelevel','submenudetails__submenu__id':'submenuid'}, inplace = True)


        finaldf = pd.DataFrame()

        if len(df.index) > 0:
            finaldf = (df.groupby(['roleid','rolename','roledesc','rolelevel'])
            .apply(lambda x: x[['submenuid']].to_dict('records'))
            .reset_index()
            .rename(columns={0:'submenudetails'})).T.to_dict().values()

        return Response(finaldf)
    



class menudetails(ListAPIView):

   
    permission_classes = (permissions.IsAuthenticated,)

      
    def get(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        entity1 = self.request.query_params.get('entity')
        role1 = self.request.query_params.get('role')
        stk = Rolepriv.objects.filter(entity = entity1,role = role1).values('submenu__mainmenu__mainmenu','submenu__mainmenu__menuurl','submenu__mainmenu__menucode','submenu__submenu','submenu__subMenuurl','submenu__submenucode').order_by('submenu__mainmenu__order')

        df = read_frame(stk)
        df.rename(columns = {'submenu__mainmenu__mainmenu':'mainmenu','submenu__mainmenu__menuurl':'menuurl','submenu__mainmenu__menucode':'menucode','submenu__submenu':'submenu','submenu__subMenuurl':'subMenuurl','submenu__submenucode':'submenucode'}, inplace = True)


        finaldf = pd.DataFrame()

        if len(df.index) > 0:
            finaldf = (df.groupby(['mainmenu','menuurl','menucode'])
            .apply(lambda x: x[['submenu','subMenuurl','submenucode']].to_dict('records'))
            .reset_index()
            .rename(columns={0:'submenu'})).T.to_dict().values()

        return Response(finaldf)
    



class entitydetailsbyuser(ListAPIView):

   
    permission_classes = (permissions.IsAuthenticated,)

      
    def get(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        # entity1 = self.request.query_params.get('entity')
        # role1 = self.request.query_params.get('role')
        
       
        stk = Userrole.objects.filter(user = self.request.user).values('user__first_name','user__last_name','user__email','role','entity__entityname','entity__state','entity__gstno','entity__id','role__id','user__id','user')

        df = read_frame(stk)
        df.rename(columns = {'user__first_name':'first_name','user__last_name':'last_name','user__email':'email','entity__entityname':'entityname','entity__state':'state','entity__gstno':'gstno','user__id':'userid','entity__id':'entityid','role__id':'roleid'}, inplace = True)


        finaldf = pd.DataFrame()

        if len(df.index) > 0:
            finaldf = (df.groupby(['userid','first_name','last_name','email','user'])
            .apply(lambda x: x[['entityid','entityname','email','gstno','role','roleid']].to_dict('records'))
            .reset_index()
            .rename(columns={0:'uentity'})).T.to_dict().values()
        else:
            stk = User.objects.filter(email = self.request.user).values('first_name','last_name','email','id')
            df = read_frame(stk)
            df.rename(columns = {'id':'userid'}, inplace = True)
            return Response(df.T.to_dict().values())


        return Response(finaldf)
    


class userdetailsbyentity(ListAPIView):

   
    permission_classes = (permissions.IsAuthenticated,)

      
    def get(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        entity = self.request.query_params.get('entity')
        # role1 = self.request.query_params.get('role')
       
        stk = Userrole.objects.filter(entity = entity).values('user__first_name','user__last_name','user__email','user__username','role__rolename','role__id','user__is_active','id')

        df = read_frame(stk)
        df.rename(columns = {'user__first_name':'first_name','user__last_name':'last_name','user__email':'email','user__username':'username','role__rolename':'rolename','role__id':'roleid','user__is_active':'is_active','id':'userid'}, inplace = True)


        # finaldf = pd.DataFrame()

        # if len(df.index) > 0:
        #     finaldf = (df.groupby(['userid','first_name','last_name','email','user'])
        #     .apply(lambda x: x[['entityid','entityname','email','gstno','role','roleid']].to_dict('records'))
        #     .reset_index()
        #     .rename(columns={0:'uentity'})).T.to_dict().values()

        return Response(df.T.to_dict().values())
    


class getgstindetails(ListAPIView):


  
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = {'id':["in", "exact"]
    
    }
    #filterset_fields = ['id']
    def get(self, request, format=None):
        entitygst = self.request.query_params.get('entitygst')

       
        if not entitygst:
            return response.Response({"error": "Entity GST parameter is required."}, status=status.HTTP_400_BAD_REQUEST)
        gst_data = get_gst_details(entitygst)

        # state_instance = State.objects.get(statecode=gst_data.get('StateCode'))


        print(gst_data['Gstin'])
        try:
            state_instance, _ = State.objects.get_or_create(statecode=gst_data['StateCode'])
            city_instance, _ = City.objects.get_or_create(pincode=gst_data['AddrPncd'])
        except Exception as e:
            return {"error": str(e)}

        # Check if GSTIN already exists
        if GstAccountsdetails.objects.filter(gstin=gst_data['Gstin']).exists():
            gstdetails = GstAccountsdetails.objects.filter(gstin=gst_data['Gstin']).values()
        else:
            new_gst = GstAccountsdetails.objects.create(
                gstin=gst_data['Gstin'],
                tradeName=gst_data['TradeName'],
                legalName=gst_data['LegalName'],
                addrFlno=gst_data['AddrFlno'],
                addrBnm=gst_data['AddrBnm'],
                addrBno=gst_data['AddrBno'],
                addrSt=gst_data['AddrSt'],
                addrLoc=city_instance,
                stateCode=state_instance,
                district=city_instance.distt,
                country=state_instance.country,
                addrPncd=gst_data['AddrPncd'],
                txpType=gst_data['TxpType'],
                status=gst_data['Status'],
                blkStatus=gst_data['BlkStatus'],
                dtReg=gst_data['DtReg'],
                dtDReg=gst_data['DtDReg']
            )
            gstdetails = [new_gst]

        # Transform data into the required format
        result = [
        {
            'gstno': detail['gstin'],
            'entityname': detail['tradeName'],
            'legalname': detail['legalName'],
            'address': detail['addrBnm'],
            'address2': detail['addrBno'],
            'addressfloorno': detail['addrFlno'],
            'addressstreet': detail['addrSt'],
            'stateid': detail['stateCode_id'],
            'pincode': detail['addrPncd'],
            'gstintype': detail['txpType'],
            'dateofreg': detail['dtReg'],
            'dateofdreg': detail['dtDReg'],
            'cityid': detail['addrLoc_id'],
            'countryid': detail['country_id'],
            'disttid': detail['district_id'],
        }
        for detail in gstdetails
    ]
    

        #return result

    


       
        return response.Response(result)






        


  
        
        

        
  

     
        
     
        return  Response(df.T.to_dict().values())
    

class EntityFinancialYearView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = EntityFinancialYearSerializerlist

    def get_queryset(self):
        entity_id = self.request.query_params.get('entity')  # Get entity from query params
        if entity_id:
            return entityfinancialyear.objects.filter(entity_id=entity_id)
        return entityfinancialyear.objects.none()  # Return empty if no entity provided
        
            
    



    


