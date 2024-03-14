from django.urls import path
from inventory import views


app_name = 'inventory'

urlpatterns  = [


    path('productcategory',views.productcategoryApiView.as_view(), name = 'productcategory'),
    path('productcategory/<int:id>',views.productcategoryupdatedelApiView.as_view(), name = 'productcategoryupdatedel'),
    path('createProduct',views.CreateTodoApiView.as_view(), name = 'product1'),
    path('ListProduct',views.ListproductApiView.as_view(), name = 'listproduct'),
    path('product',views.productApiView.as_view(), name = 'product'),
    path('product/<int:id>',views.productupdatedel.as_view(), name = 'product2'),
    path('album',views.AlbumApiView.as_view(), name = 'Album'),
    path('album/<int:id>',views.Albumupdatedel.as_view(), name = 'Album2'),
    path('track',views.TrackApiView.as_view(), name = 'Track'),
    path('<int:id>',views.TrackApiView.as_view(), name = 'track2'),
    path('tog',views.togApiView.as_view(), name = 'tog'),
    path('gst',views.gstApiView.as_view(), name = 'tog'),
    path('ratecalculator',views.rateApiView.as_view(), name = 'ratecalculator'),
    path('uom',views.uomApiView.as_view(), name = 'uom'),
    path('hsn',views.hsnApiView.as_view(), name = 'uom'),

    
    
   
] 