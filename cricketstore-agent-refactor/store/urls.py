from django.urls import path
from . import views
from django.contrib.auth.views import LogoutView
urlpatterns = [
    path('',views.homepage,name='homepage'),
    path('store/', views.store, name="store"),
	path('store/<int:category_id>/', views.store, name="store"),
    path('productdetail/<int:pk>/',views.product_detail,name='productdetail'),
	path('cart/', views.cart, name="cart"),
	path('checkout/', views.checkout, name="checkout"),
    path('update-item/',views.updateItem,name='update-item'),
    path('login/',views.loginview,name='login'),
    path('signup/',views.signupview,name='signup'),
    path('logout/',LogoutView.as_view(),name='logout'),
    path('profile/',views.profileview,name='profile'),
    path('myorders/',views.myorders,name='myorders'),
    path('search/',views.search_suggestions,name='search'),
    path("upload-photo/", views.upload_photo, name="upload_photo"),
]

