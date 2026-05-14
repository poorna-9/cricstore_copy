from pyclbr import Class
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta,datetime,date
import requests
import uuid


class Customer(models.Model):
    user=models.OneToOneField(User,on_delete=models.CASCADE,null=True,blank=True,related_name='bookings_customer')
    name=models.CharField(max_length=50,null=True)
    email=models.EmailField(max_length=50,null=True)
    phone = models.CharField(max_length=15, null=True, blank=True)
    
    def __str__(self):
        return self.name or ""

class Ground(models.Model):
    SPORT_CHOICES = [
     ('cricket', 'Cricket'),
     ('football', 'Football'),
     ('tennis', 'Tennis'),
     ('badminton', 'Badminton'),
     ('volleyball', 'Volleyball'),
     ('basketball', 'Basketball'),
     ('hockey', 'Hockey')]
    GROUND_TYPE_CHOICES = [
      ('turf', 'Turf'),
      ('ground', 'Ground'),
     ]
    name=models.CharField(max_length=100,unique=True,null=False)
    types=models.CharField(max_length=50,null=False,choices=GROUND_TYPE_CHOICES,default='turf')
    city=models.CharField(max_length=100,null=False)
    address=models.TextField(null=False)
    price = models.DecimalField(max_digits=8, decimal_places=2, null=True,blank=True)
    image = models.ImageField(upload_to='grounds/',null=True,blank=True)
    sporttype=models.CharField(max_length=50,null=False,choices=SPORT_CHOICES,default='cricket')
    lattitude=models.FloatField(null=True,blank=True)
    longitude=models.FloatField(null=True,blank=True)
    rating=models.FloatField(null=True,blank=True)
    opens= models.BooleanField(default=True)
    batballprovided=models.BooleanField(default=True)
    washroomsavailable=models.BooleanField(default=False)
    Grounddimensions=models.CharField(max_length=100,null=True,blank=True)
    morning_price=models.IntegerField(null=True,blank=True)
    afternoon_price=models.IntegerField(null=True,blank=True)
    evening_price=models.IntegerField(null=True,blank=True)
    night_price=models.IntegerField(null=True,blank=True)
    t_morning_price=models.IntegerField(null=True,blank=True)
    t_afternoon_price=models.IntegerField(null=True,blank=True)
    t_evening_price=models.IntegerField(null=True,blank=True)
    t_night_price=models.IntegerField(null=True,blank=True)
    t_fullday_price=models.IntegerField(null=True,blank=True)
    def __str__(self):
        return self.name
    @property
    def imageURL(self):
        try:
            url = self.image.url
        except:
            url = ''
        return url
    
    def save(self,*args,**kwargs):
        if not self.lattitude or not self.longitude:
            LOCATIONIQ_API_KEY="pk.9a6225b4ea47b4e24c62938d1d821a4f"
            url="https://us1.locationiq.com/v1/search"
            params={"address":self.address,"key": LOCATIONIQ_API_KEY,"format": "json"}
            headers = {"User-Agent": "CricStore-App/1.0"}
            response=requests.get(url,params=params,headers=headers)
            data=response.json()
            if isinstance(data, list) and data:
                loc=data[0]
                self.lattitude=loc['lat']
                self.longitude=loc['lng']
        super().save(*args,**kwargs)

class slots(models.Model):
    ground = models.ForeignKey(Ground, on_delete=models.CASCADE, related_name='slots')
    starttime=models.TimeField()
    endtime=models.TimeField()
    date = models.DateField()  
    shift = models.CharField(
    max_length=20,
    choices=[
        ("morning", "Morning"),
        ("afternoon", "Afternoon"),
        ("evening", "Evening"),
        ("night", "Night"),
    ]
    )                  
    is_booked = models.BooleanField(default=False)
    is_blocked=models.BooleanField(default=False)
    price=models.IntegerField(null=True,blank=True)
    blocked_at = models.DateTimeField(null=True, blank=True) 
    def __str__(self):
        return f"{self.ground.name} {self.date} {self.starttime.strftime('%I:%M %p')} - {self.endtime.strftime('%I:%M %p')}"
    
class tournamentsession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    ground = models.ForeignKey(Ground, on_delete=models.CASCADE)
    start_date = models.DateField(null=True,blank=True)
    end_date = models.DateField(null=True,blank=True)
    session_type = models.CharField(
    max_length=20,
    choices=[
        ("morning", "Morning"),
        ("afternoon", "Afternoon"),
        ("evening", "Evening"),
        ("night", "Night"),
        ("full_day", "Full Day"),
    ],
    default="full_day"   
     )
class reservetournament(models.Model):
    session = models.ForeignKey(tournamentsession, on_delete=models.CASCADE)
    ground = models.ForeignKey(Ground, on_delete=models.CASCADE)
    date = models.DateField()
    blocked_slots = models.ManyToManyField(
        'slots',
        related_name='tournament_days'
    )
    status = models.CharField(max_length=10, choices=[('reserved', 'Reserved'), ('booked', 'Booked')])
    session_type = models.CharField(
        max_length=20,
        choices=[
            ("morning", "Morning"),
            ("afternoon", "Afternoon"),
            ("evening", "Evening"),
            ("night", "Night"),
            ("full_day", "Full Day"),
        ],default="full_day" 
    )
    class Meta:
        constraints = [
        models.UniqueConstraint(
            fields=["ground", "date"],
            condition=models.Q(status__in=["reserved", "booked"]),
            name="unique_active_tournament_day"
        )
    ]

class reservationsession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user=models.ForeignKey(User,on_delete=models.CASCADE)
    ground = models.ForeignKey(Ground, on_delete=models.CASCADE)
    date=models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)


class Orders(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    ground = models.ForeignKey('Ground', on_delete=models.CASCADE)
    normal_session = models.ForeignKey(
        reservationsession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    tournament_session= models.ForeignKey(tournamentsession,on_delete=models.SET_NULL,null=True,blank=True)  
    date = models.DateField()
    slotsbooked = models.ForeignKey('slots', on_delete=models.CASCADE, null=True, blank=True)
    transaction_id = models.CharField(max_length=100)
    booked = models.BooleanField(default=False)
    payment_status = models.BooleanField(default=False)
    price = models.FloatField(default=0.0)
    Tournament_or_normal = models.CharField(max_length=20, default='normal')
    refund_amount = models.FloatField(default=0.0)
    cancel_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.ground.name} on {self.date}"
   
class Bookings(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    ground = models.ForeignKey(Ground, on_delete=models.CASCADE)
    date = models.DateField()
    slotsbooked = models.ManyToManyField(slots)
    transaction_id = models.CharField(max_length=100)
    booked = models.BooleanField(default=False)
    price = models.FloatField(default=0.0)
    payment_status = models.BooleanField(default=False)
    refund_amount = models.FloatField(default=0.0)
    cancel_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    

class reservedslots(models.Model):
    STATUS_CHOICES = [
        ('reserved', 'Reserved'),
        ('booked', 'Booked')
    ]
    session=models.ForeignKey(reservationsession,on_delete=models.CASCADE)
    slot = models.ForeignKey(slots, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='reserved')
    class Meta:
        unique_together = ('slot',)
    def __str__(self):
        return f"{self.slot} - {self.status}"
    

class payment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    session = models.ForeignKey(
        reservationsession,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    tournament_session = models.ForeignKey(
        tournamentsession,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    order_id = models.CharField(max_length=100, null=True, blank=True)
    payment_id = models.CharField(max_length=100, null=True, blank=True)
    stripe_session_id = models.CharField(max_length=255, null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    amount = models.FloatField()
    status = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

class Booking(models.Model):
    booking_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(payment, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    ground = models.ForeignKey(Ground, on_delete=models.CASCADE)
    date = models.DateField()
    slots = models.ManyToManyField(slots)
    total_price = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)
    
