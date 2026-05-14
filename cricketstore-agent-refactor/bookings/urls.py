from django.urls import URLPattern, path
from . import views
from django.contrib.auth.views import LogoutView
urlpatterns=[
    path('',views.selectcity,name='select_city'),
    path('grounds/',views.checkpage,name='grounds_page'),
    path('grounddetail/<int:pk>/',views.grounddetail,name='grounddetail'),
    path('get_reserved_slots/',views.getreservedslots,name='getreservedslots'), # type: ignore
    path('reserveslot/',views.reserveslot,name='reserve_slot'),
    path('checkout/<uuid:session_id>/', views.checkoutpage, name='checkout'),
    path('payment/success/', views.payment_success_page, name='payment_success_page'),
    path('payment/cancel/', views.payment_cancel_page, name='payment_cancel_page'),
    path('payment-success/', views.payment_success, name='payment_success'),
    path("stripe/webhook/", views.payment_success_stripe, name="stripe_webhook"),
    path('bookingthroughagent/',views.bookingagent,name="bookingthroughagent"),
    path('booking-agent/',views.bookingagent,name='booking_agent'),
    path('booking-agent/chat/',views.userquerychatbot,name='userquerychatbot'),
    path('get_user_location/',views.getuserlocation,name="get_user_location"),
    path('tournament-booking/<int:pk>/',views.tournamentBookingPage,name='tournamentBookingPage'),
    path('reservetournamentday/',views.reservetournamentday,name='reservetournamentday'), 
    path('gettournamentreserveddays/',views.gettournamentreserveddays,name='gettournamentreserveddays'),
    path('tournamentcheckout/<uuid:session_id>/',views.tournamentcheckout,name="tournamentcheckout"),
]

