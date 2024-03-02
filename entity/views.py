from django.http import request
from django.shortcuts import render

from rest_framework.generics import CreateAPIView,ListAPIView,ListCreateAPIView,RetrieveUpdateDestroyAPIView,GenericAPIView
from entity.models import entity,entity_details,unitType,entityfinancialyear,Constitution,subentity,Rolepriv,Role,Userrole
from entity.serializers import entitySerializer,entityDetailsSerializer,unitTypeSerializer,entityAddSerializer,entityfinancialyearSerializer,entityfinancialyearListSerializer,ConstitutionSerializer,subentitySerializer,subentitySerializerbyentity,roleSerializer,rolemainSerializer
from rest_framework import permissions
from django_filters.rest_framework import DjangoFilterBackend
from Authentication.models import User
from django_pandas.io import read_frame
import numpy as np
import pandas as pd
from rest_framework.response import Response




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

    def perform_create(self, serializer):
        return serializer.save(user = [self.request.user])
    
    def get_queryset(self):
        return entity.objects.filter(user = self.request.user)





class entityApiView(ListCreateAPIView):

    serializer_class = entitySerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']

    def perform_create(self, serializer):
        return serializer.save()
    
    def get_queryset(self):
        return entity.objects.filter(user = self.request.user)






class entityupdatedel(RetrieveUpdateDestroyAPIView):

    serializer_class = entitySerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        return entity.objects.filter()

# class entityLoadApiView(ListCreateAPIView):

#     serializer_class = entitySerializer
#     permission_classes = (permissions.IsAuthenticated,)

#     filter_backends = [DjangoFilterBackend]
#     filterset_fields = ['id','unitType','entityName']

        
#     def get_queryset(self):
#         return entity.objects.filter()

class entityDetailsApiView(ListCreateAPIView):

    serializer_class = entityDetailsSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['style']

    def perform_create(self, serializer):
        return serializer.save(owner = self.request.user)
    
    def get_queryset(self):
        return entity_details.objects.filter(owner = self.request.user)


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
    

class entityfinancialyearApiView(ListCreateAPIView):

    serializer_class = entityfinancialyearSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        return entityfinancialyear.objects.filter(isactive = 1).order_by('-isactive')
    

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

    serializer_class = rolemainSerializer
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

    serializer_class = rolemainSerializer
    
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
        stk = Role.objects.prefetch_related('roledetails').filter(entity = entity1,id = role1).values('roledetails__submenu__submenu','roledetails__submenu__subMenuurl','roledetails__submenu__id','id','rolename','roledesc','rolelevel')

        df = read_frame(stk)
        df.rename(columns = {'id':'roleid','rolename':'rolename','roledesc':'roledesc','rolelevel':'rolelevel','roledetails__submenu__submenu':'submenu','roledetails__submenu__subMenuurl':'subMenuurl'}, inplace = True)


        finaldf = pd.DataFrame()

        if len(df.index) > 0:
            finaldf = (df.groupby(['roleid','rolename','roledesc','rolelevel'])
            .apply(lambda x: x[['submenu','subMenuurl']].to_dict('records'))
            .reset_index()
            .rename(columns={0:'roledetails'})).T.to_dict().values()

        return Response(finaldf)
    



class menudetails(ListAPIView):

   
    permission_classes = (permissions.IsAuthenticated,)

      
    def get(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        entity1 = self.request.query_params.get('entity')
        role1 = self.request.query_params.get('role')
        stk = Rolepriv.objects.filter(entity = entity1,role = role1).values('submenu__mainmenu__mainmenu','submenu__mainmenu__menuurl','submenu__mainmenu__menucode','submenu__submenu','submenu__subMenuurl').order_by('mainmenu__order')

        df = read_frame(stk)
        df.rename(columns = {'submenu__mainmenu__mainmenu':'mainmenu','submenu__mainmenu__menuurl':'menuurl','submenu__mainmenu__menucode':'menucode','submenu__submenu':'submenu','submenu__subMenuurl':'subMenuurl'}, inplace = True)


        finaldf = pd.DataFrame()

        if len(df.index) > 0:
            finaldf = (df.groupby(['mainmenu','menuurl','menucode'])
            .apply(lambda x: x[['submenu','subMenuurl']].to_dict('records'))
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

        return Response(finaldf)
        
            
    



    


