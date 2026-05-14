from django.db import models
from django.contrib.auth.models import User
class Category(models.Model):
    name=models.CharField(max_length=50)
    def __str__(self):
        return self.name
class Customer(models.Model):
    user=models.OneToOneField(User,on_delete=models.CASCADE,null=True,blank=True,related_name='store_customer' )
    name=models.CharField(max_length=50,null=True)
    email=models.EmailField(max_length=50,null=True)

    def __str__(self):
        return self.name or ""

class Product(models.Model):
    name=models.CharField(max_length=75)
    category=models.ForeignKey(Category,on_delete=models.CASCADE,null=True,blank=True)
    colour=models.CharField(max_length=100,null=True,blank=True)
    price=models.FloatField()
    digital=models.BooleanField(default=False,null=True,blank=True)
    image=models.ImageField(null=True,blank=True )
    manufacturer=models.CharField(max_length=100,null=True,blank=True)
    description=models.CharField(max_length=2000,null=True,blank=True)
    material=models.CharField(max_length=50,null=True,blank=True)
    
    def __str__(self):
        return self.name
    
    @property
    def imageURL(self):
     try:
        url = self.image.url
     except:
        url = ''
     return url

class Order(models.Model):
    customer=models.ForeignKey(Customer,on_delete=models.SET_NULL,blank=True,null=True)
    date_ordered=models.DateTimeField(auto_now_add=True)
    complete=models.BooleanField(default=False,null=True,blank=True)
    transaction_id=models.CharField(max_length=100,null=True)
    @property
    def get_cart_total(self):
        orderitems=self.orderitem_set.all()
        total=sum([item.get_total for item in orderitems])
        return total
    
    @property
    def get_cart_items(self):
      return sum([item.quantity for item in self.orderitem_set.all()])
    def __str__(self):
        return str(self.id)
class Orderitem(models.Model):
    product=models.ForeignKey(Product,on_delete=models.SET_NULL,blank=True,null=True)
    order=models.ForeignKey(Order,on_delete=models.SET_NULL,blank=True,null=True)
    quantity=models.IntegerField(default=0,null=True,blank=True)
    date_added=models.DateTimeField(auto_now_add=True)
    size = models.CharField(max_length=5, default='M')
    @property
    def get_total(self):
        total=self.product.price*self.quantity
        return total

class Shippingaddress(models.Model):
    customer=models.ForeignKey(Customer,on_delete=models.SET_NULL,blank=True,null=True)
    order=models.ForeignKey(Order,on_delete=models.SET_NULL,blank=True,null=True)
    address=models.CharField(max_length=200,null=True)
    city=models.CharField(max_length=75,null=True)
    state=models.CharField(max_length=75,null=True)
    zipcode=models.CharField(max_length=20,null=True)
    date_added=models.DateTimeField(auto_now_add=True)
    label = models.CharField(max_length=50, default='Home')
    def __str__(self):
        return f"{self.label} - {self.address}, {self.city}"
    
