from django.db import models
from helpers.models import TrackingModel
from django.contrib.auth.models import AbstractBaseUser,PermissionsMixin, UserManager
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.apps import apps
from django.utils import timezone
from django.utils.translation import gettext as _
from django.contrib.auth.hashers import make_password
import jwt;
from django.conf import Settings, settings
from datetime import datetime, timedelta
#from entity.models import entity


# Create your models here.


class MyUserManager(UserManager):
    def _create_user(self, username, email, password, **extra_fields):
        """
        Create and save a user with the given username, email, and password.
        """
        if not username:
            raise ValueError('The given username must be set')
        if not email:
            raise ValueError('The given username must be set')
        email = self.normalize_email(email)
        # Lookup the real model class from the global app registry so this
        # manager method can be used in migrations. This is fine because
        # managers are by definition working on the real model.
        GlobalUserModel = apps.get_model(self.model._meta.app_label, self.model._meta.object_name)
        username = GlobalUserModel.normalize_username(username)
        user = self.model(username=username, email=email, **extra_fields)
        user.password = make_password(password)
        user.save(using=self._db)
        return user

    def create(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(username, email, password, **extra_fields)

    def create_user(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(username, email, password, **extra_fields)



class Role(TrackingModel):
    rolename = models.CharField(max_length=150)
    roledesc = models.CharField(max_length=150)
    







class User(AbstractBaseUser,PermissionsMixin,TrackingModel,UserManager):
    username_validator = UnicodeUsernameValidator()

    username = models.CharField(
    _('username'),
        max_length=150,
       # unique=True,
        help_text=_('Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.'),
        #validators=[username_validator],
        error_messages={
            'unique': _("A user with that username already exists."),
        },
    )
    first_name = models.CharField(_('first name'), max_length=100, blank=True)
    last_name = models.CharField(_('last name'), max_length=100, blank=True)
    email = models.EmailField(_('email address'), blank=False,unique = True)
    role = models.ForeignKey(Role, on_delete=models.CASCADE,null=True,blank=True)
    is_staff = models.BooleanField(
        _('staff status'),
        default=False,
        help_text=_('Designates whether the user can log into this admin site.'),
    )
    is_active = models.BooleanField(
        _('active'),
        default=True,
        help_text=_(
            'Designates whether this user should be treated as active. '
            'Unselect this instead of deleting accounts.'
        ),
    )
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)
    email_verified = models.BooleanField(
        _('emailVerified'),
        default=True,
        help_text=_(
            'Email Verification '
            
        ),
    )


    objects = MyUserManager()

    EMAIL_FIELD = 'email'
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']


    @property
    def token(self):
        token = jwt.encode({'username':self.username,'email':self.email,'exp': datetime.utcnow() + timedelta(hours= 360)},settings.SECRET_KEY,
        algorithm='HS256'
         )
        return token

class MainMenu(TrackingModel):
    mainmenu = models.CharField(max_length=50) 
    menuurl = models.CharField(max_length=50, null=True,blank=True)
    menucode = models.CharField(max_length=50)

    class Meta:
        verbose_name = _('Menu')
        verbose_name_plural = _('Menus')


    
    def __str__(self):
        return f'{self.mainmenu}'

class submenu(TrackingModel):
    mainmenu =     models.ForeignKey(MainMenu, on_delete=models.CASCADE,null= True,related_name='submenu')
    submenu =      models.CharField(max_length=50)
    subMenuurl =   models.CharField(max_length=50)


    class Meta:
        verbose_name = _('submenu')
        verbose_name_plural = _('submenu')


    
    def __str__(self):
        return f'{self.submenu}'


class rolepriv(TrackingModel):
    role =     models.ManyToManyField(Role,null= True,related_name='roles')
    mainmenu =     models.ManyToManyField(MainMenu,null= True,related_name='mainmenus')
 


    class Meta:
        verbose_name = _('Role Priveledge')
        verbose_name_plural = _('Role Priveledges')


    
    def __str__(self):
        return f'{self.role}'

