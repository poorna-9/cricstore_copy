from django.urls import URLPattern, path
from . import views
from django.contrib.auth.views import LogoutView


urlpatterns = [
    path('', views.selectcity, name='select_city'),
    path('grounds/', views.checkpage, name='grounds_page'),
    path('grounddetail/<int:pk>/', views.grounddetail, name='grounddetail'),
    path('get_reserved_slots/', views.getreservedslots, name='getreservedslots'),
    path('reserveslot/', views.reserveslot, name='reserve_slot'),
    path('checkout/<uuid:session_id>/', views.checkoutpage, name='checkout'),
    path('payment/cancel/', views.payment_cancel_page, name='payment_cancel_page'),
    path('payment_success_razorpay/', views.payment_success_razorpay, name='payment_success_razorpay'),
    path('payment_success_page/', views.payment_success_page, name='payment_success_page'),
    path('razorpay_webhook/', views.payment_success_razorpay_webhook, name='razorpay_webhook'),
    path('bookingthroughagent/', views.bookingagent, name="bookingthroughagent"),
    path('booking-agent/', views.bookingagent, name='booking_agent'),
    path('booking-agent/chat/', views.userquerychatbot, name='userquerychatbot'),
    path('get_user_location/', views.getuserlocation, name="get_user_location"),
    path('tournament-booking/<int:pk>/', views.tournamentBookingPage, name='tournamentBookingPage'),
    path('reservetournamentday/', views.reservetournamentday, name='reservetournamentday'),
    path('gettournamentreserveddays/', views.gettournamentreserveddays, name='gettournamentreserveddays'),
    path('tournamentcheckout/<uuid:session_id>/', views.tournamentcheckout, name="tournamentcheckout"),
    path('payment_waiting/<str:razorpay_order_id>/', views.payment_waiting_page, name='payment_waiting_page'),
    path('create_razorpay_order/<uuid:session_id>/', views.create_razorpay_order, name='create_razorpay_order'),
    path('check_payment_status/<str:razorpay_order_id>/', views.check_payment_status, name='check_payment_status'),
    path('create_tournament_razorpay_order/<uuid:session_id>/', views.create_tournament_razorpay_order, name='create_tournament_razorpay_order'),
    path('booking/<uuid:booking_id>/', views.booking_detail, name='booking_detail'),
    path('cancel_booking/<uuid:booking_id>/', views.cancel_booking_view, name='cancel_booking'),
    path('my_bookings/', views.my_bookings, name='my_bookings'),
]
