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
    path('ProductList', views.ProductListView.as_view(), name='hsn'),
    path('bulk-insert-products', views.BulkProductCreateView.as_view(), name='bulk-insert-products'),
    path('bulk-create/<int:entity_id>/', views.ProductBulkCreateAPIView.as_view(), name='bulk-insert-products'),
    path('InvoiceBulkCreate/<int:entity_id>/', views.ProductBulkCreateAPIView.as_view(), name='invoice-bulk-create'),
    path('boms/', views.BillOfMaterialAPIView.as_view(), name='bom-list-create'),
    path('boms/<int:pk>/', views.BillOfMaterialAPIView.as_view(), name='bom-detail-update-delete'),
    path('production-orders/', views.ProductionOrderAPIView.as_view(), name='production-order-list-create'),
    path('production-orders/<int:pk>/', views.ProductionOrderAPIView.as_view(), name='production-order-detail'),
    path('bomlist/', views.BillOfMaterialListAPIView.as_view(), name='bom-list'),
    path('bom-items-calculated/', views.BOMItemCalculatedAPIView.as_view(), name='bom-items-calculated'),
    path('bomlistbyentity/', views.BillOfMaterialListbyentityView.as_view(), name='bom-list'),
    path('production-orders-List/', views.ProductionOrderListView.as_view(), name='production-order-list'),
   # path("api/products/", ProductBulkCreateAPIView.as_view(), name="product-bulk-create"),


   


    
                                            ]
