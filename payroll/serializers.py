from rest_framework import serializers
from payroll.models import salarycomponent,employee,employeesalary,salarytrans,department,designation
from Authentication.serializers import Registerserializers
from Authentication.models import User
from django.contrib.auth.hashers import make_password


class salarycomponentserializer(serializers.ModelSerializer):
    #id = serializers.IntegerField()
    class Meta:
        model = salarycomponent
        fields = ('id','salarycomponentname','salarycomponentcode','componentperiod','componenttype','defaultpercentage','entity','createdby',)

class employeeserializer(serializers.ModelSerializer):

    employee = Registerserializers(many=False)

    


    def create(self, validated_data):
        #print(validated_data)
        emp = validated_data.pop('employee')

        try:
            
            employeeid = User.objects.create(**emp)
        except Exception as e:
            error = {'message': ",".join(e.args) if len(e.args) > 0 else 'Unknown Error'}
            raise serializers.ValidationError(error)
        
        

        id = employee.objects.create(employee = employeeid,**validated_data)

        return id
    
    def update(self, instance, validated_data):

        fields = ['entity','createdby','employeeid','dateofjoining','department','designation','reportingmanager','bankname','bankaccountno','pan','address1','address2','country','state','district','city',]
        for field in fields:
            try:
                setattr(instance, field, validated_data[field])
            except KeyError:  # validated_data may not contain all fields during HTTP PATCH
                pass
        
        instance.save()

        emp = validated_data.pop('employee')

        id = emp.pop('id')

       # print(email)

        password = emp.pop('password')
        password = make_password(password)

        print(emp)

        try:
            employeeid = User.objects.filter(id = id).update(**emp,password=password)

            return instance
        
        except Exception as e:
            error = {'message': ",".join(e.args) if len(e.args) > 0 else 'Unknown Error'}
            raise serializers.ValidationError(error)

        







    #id = serializers.IntegerField()
    class Meta:
        model = employee
        fields = ('employee','employeeid','dateofjoining','department','entity','createdby','designation','reportingmanager','bankname','bankaccountno','pan','address1','address2','country','state','district','city',)
        #depth = 1




class employeesalaryserializer(serializers.ModelSerializer):
    #id = serializers.IntegerField()
    class Meta:
        model = employeesalary
        fields = ('id','employee','scomponent','percentageofctc','salaryvalue','entity','createdby','isactive',)


class salarytransserializer(serializers.ModelSerializer):
    #id = serializers.IntegerField()
    class Meta:
        model = salarytrans
        fields = ('id','salaryamountexpected','salaryamountactual','percentageofctc','salaryvalue','entity','createdby','isactive',)

class departmentserializer(serializers.ModelSerializer):
    #id = serializers.IntegerField()
    class Meta:
        model = department
        fields = ('id','departmentname','departmentcode',)


class designationserializer(serializers.ModelSerializer):
    #id = serializers.IntegerField()
    class Meta:
        model = designation
        fields = ('id','designationname','designationcode',)



class reportingmanagerserializer(serializers.ModelSerializer):
    #id = serializers.IntegerField()
    class Meta:
        model = User
        fields = ('id','first_name',)


