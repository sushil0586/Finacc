from django.urls import path
from inventory import views

app_name = 'inventory'

urlpatterns = [
    # Product Category
    path('productcategory', views.ProductCategoryApiView.as_view(), name='productcategory'),
    path('productcategory/<int:id>', views.ProductCategoryUpdateDeleteApiView.as_view(), name='productcategoryupdate'),

    # Product
    # path('createProduct', views.CreateTodoApiView.as_view(), name='createProduct'),
    # path('listProduct', views.ListproductApiView.as_view(), name='listProduct'),
    path('product', views.ProductApiView.as_view(), name='product'),
    path('product/<int:id>', views.ProductUpdateDeleteApiView.as_view(), name='productupdate'),

    # Album
    path('album', views.AlbumApiView.as_view(), name='album'),
    path('album/<int:id>', views.AlbumUpdateDeleteApiView.as_view(), name='albumupdate'),

    # Track
    path('track', views.TrackApiView.as_view(), name='track'),
    path('track/<int:id>', views.TrackApiView.as_view(), name='trackupdate'),  # You had a duplicate path here, renamed to 'trackupdate'

    # Type of Goods (TOG)
    path('tog', views.TOGApiView.as_view(), name='tog'),

    # GST
    path('gst', views.GSTApiView.as_view(), name='gst'),

    # Rate Calculator
    path('ratecalculator', views.RateApiView.as_view(), name='ratecalculator'),

    # Unit of Measurement (UOM)
    path('uom', views.UOMApiView.as_view(), name='uom'),

    # HSN Code
    path('hsn', views.HSNApiView.as_view(), name='hsn'),
]
