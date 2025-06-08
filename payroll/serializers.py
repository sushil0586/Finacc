from rest_framework import serializers
from payroll.models import salarycomponent,employeesalary,salarytrans,department,designation,EmployeePayrollComponent,EntityPayrollComponentConfig,employeenew, CalculationType, BonusFrequency, CalculationValue, ComponentType,PayrollComponent
from Authentication.serializers import Registerserializers
from Authentication.models import User
from django.contrib.auth.hashers import make_password


class salarycomponentserializer(serializers.ModelSerializer):
    #id = serializers.IntegerField()
    class Meta:
        model = salarycomponent
        fields = ('id','salarycomponentname','salarycomponentcode','componentperiod','componenttype','defaultpercentage','entity','createdby','calculationtype',)

# class employeeserializer(serializers.ModelSerializer):

#     employee = Registerserializers(many=False)

    


#     def create(self, validated_data):
#         #print(validated_data)
#         emp = validated_data.pop('employee')
#         emp.pop('id')

#         try:
            
#             employeeid = User.objects.create(**emp)
#         except Exception as e:
#             error = {'message': ",".join(e.args) if len(e.args) > 0 else 'Unknown Error'}
#             raise serializers.ValidationError(error)
        
        

#         id = employee.objects.create(employee = employeeid,**validated_data)

#         return id
    
#     def update(self, instance, validated_data):

#         fields = ['entity','createdby','employeeid','dateofjoining','department','designation','reportingmanager','bankname','bankaccountno','pan','address1','address2','country','state','district','city','isactive',]
#         for field in fields:
#             try:
#                 setattr(instance, field, validated_data[field])
#             except KeyError:  # validated_data may not contain all fields during HTTP PATCH
#                 pass
        
#         instance.save()

#         emp = validated_data.pop('employee')

#         id = emp.pop('id')

#        # print(email)

#         password = emp.pop('password')
#         password = make_password(password)

#         print(emp)

#         try:
#             employeeid = User.objects.filter(id = id).update(**emp,password=password)

#             return instance
        
#         except Exception as e:
#             error = {'message': ",".join(e.args) if len(e.args) > 0 else 'Unknown Error'}
#             raise serializers.ValidationError(error)

        







#     #id = serializers.IntegerField()
#     class Meta:
#         model = employee
#         fields = ('employee','employeeid','dateofjoining','department','entity','createdby','designation','reportingmanager','bankname','bankaccountno','pan','address1','address2','country','state','district','city','isactive',)
#         #depth = 1




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



# class employeeListSerializer(serializers.ModelSerializer):



#     employeeid = serializers.IntegerField(source = 'employee')
#     email =  serializers.CharField(max_length=500,source = 'employee__email')
#     #caccountheadname =  serializers.CharField(max_length=500,source = 'creditaccounthead__name')
  

    

    




    

#     class Meta:
#         model = employee
#         fields =  ('employeeid','email',)


# class employeeListfullSerializer(serializers.ModelSerializer):



#     employeeid = serializers.IntegerField(source = 'employee')
#     email =  serializers.CharField(max_length=500,source = 'employee__email')
#     firstname =  serializers.CharField(max_length=500,source = 'employee__first_name')
#     lastname =  serializers.CharField(max_length=500,source = 'employee__last_name')
#     employee_id =  serializers.CharField(max_length=500,source = 'employeeid')
#     #caccountheadname =  serializers.CharField(max_length=500,source = 'creditaccounthead__name')
  

    

    




    

#     class Meta:
#         model = employee
#         fields =  ('employeeid','email','firstname','lastname','employee_id',)


class EmployeePayrollComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeePayrollComponent
        fields = [
            'id', 'component', 'default_value', 'is_opted_in',
            'overridden_value', 'final_value'
        ]

class EmployeeSerializer(serializers.ModelSerializer):
    payroll_components = EmployeePayrollComponentSerializer(
        many=True,
        source='employeepayrollcomponent_set',
        required=False
    )

    class Meta:
        model = employeenew
        fields = ['firstname','lastname','middlename','email','password','employeeid','is_active','role','username',
            'tax_regime', 'dateofjoining', 'department', 'designation',
            'reportingmanager', 'bankname', 'bankaccountno', 'pan', 'address1', 'address2',
            'country', 'state', 'district', 'city', 'entity', 'createdby','id',
            'payroll_components'
        ]

    def create(self, validated_data):
        payroll_data = validated_data.pop('employeepayrollcomponent_set', [])
        emp = employeenew.objects.create(**validated_data)

        for component_data in payroll_data:
            EmployeePayrollComponent.objects.create(employee=emp, **component_data)
        return emp

    def update(self, instance, validated_data):
        payroll_data = validated_data.pop('employeepayrollcomponent_set', [])

        # Update employee fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update payroll components (upsert logic)
        existing_ids = [item.id for item in instance.employeepayrollcomponent_set.all()]
        sent_ids = []

        for comp_data in payroll_data:
            comp_id = comp_data.get('id', None)
            if comp_id and comp_id in existing_ids:
                # Update existing component
                epc = EmployeePayrollComponent.objects.get(id=comp_id, employee=instance)
                for attr, value in comp_data.items():
                    setattr(epc, attr, value)
                epc.save()
                sent_ids.append(comp_id)
            else:
                # Create new component
                epc = EmployeePayrollComponent.objects.create(employee=instance, **comp_data)
                sent_ids.append(epc.id)

        # Optionally delete components not sent in update
        EmployeePayrollComponent.objects.filter(employee=instance).exclude(id__in=sent_ids).delete()

        return instance
    

class EntityPayrollComponentConfigSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='component.id')
    name = serializers.CharField(source='component.name')
    componenttype = serializers.CharField(source='component.component_type.name')

    class Meta:
        model = EntityPayrollComponentConfig
        fields = ['id', 'name', 'default_value','componenttype', 'min_value', 'max_value']



class CalculationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalculationType
        fields = '__all__'

class BonusFrequencySerializer(serializers.ModelSerializer):
    class Meta:
        model = BonusFrequency
        fields = '__all__'

class CalculationValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalculationValue
        fields = '__all__'

class ComponentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComponentType
        fields = '__all__'


class EntityPayrollComponentConfigSerializerlist(serializers.ModelSerializer):
    class Meta:
        model = EntityPayrollComponentConfig
        fields = ['id', 'entity', 'default_value', 'selected_amount', 'min_value', 'max_value', 'is_active']


class PayrollComponentSerializer(serializers.ModelSerializer):
    configs = EntityPayrollComponentConfigSerializerlist(many=True, write_only=True)

    class Meta:
        model = PayrollComponent
        fields = [
            'id', 'name', 'code', 'component_type', 'calculation_type',
            'is_taxable', 'is_mandatory', 'is_basic', 'entity',
            'bonus_frequency', 'formula_expression', 'configs'
        ]

    def create(self, validated_data):
        configs_data = validated_data.pop('configs', [])
        component = PayrollComponent.objects.create(**validated_data)
        for config_data in configs_data:
            EntityPayrollComponentConfig.objects.create(component=component, **config_data)
        return component

    def update(self, instance, validated_data):
        configs_data = validated_data.pop('configs', [])

        # Update parent fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        existing_ids = []
        incoming_ids = []

        for config_data in configs_data:
            config_id = config_data.get('id', 0)
            if config_id:
                try:
                    config_instance = EntityPayrollComponentConfig.objects.get(id=config_id, component=instance)
                    for attr, value in config_data.items():
                        if attr != 'id':
                            setattr(config_instance, attr, value)
                    config_instance.save()
                    incoming_ids.append(config_id)
                except EntityPayrollComponentConfig.DoesNotExist:
                    continue  # Skip invalid id
            else:
                new_config = EntityPayrollComponentConfig.objects.create(component=instance, **config_data)
                incoming_ids.append(new_config.id)

        # Delete records not present in incoming data
        existing_ids = list(
            EntityPayrollComponentConfig.objects.filter(component=instance).values_list('id', flat=True)
        )
        to_delete = set(existing_ids) - set(incoming_ids)
        EntityPayrollComponentConfig.objects.filter(id__in=to_delete).delete()

        return instance




