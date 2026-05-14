from django.shortcuts import render,get_object_or_404
from django.http import JsonResponse,HttpResponse
from django.contrib.auth import authenticate,login
from django.core.exceptions import ValidationError
from .models import *
from django.contrib.auth.forms import AuthenticationForm
import json
from .utils import cookiecart
from .document import ProductDocument
from ai.store import interpret_product_query
def search_results(query):
    gptresults= interpret_product_query(query)
    search = ProductDocument.search().query(
        "multi_match",
        query=query,
        fields=["name", "manufacturer", "description","price","colour","material"],
        fuzziness="AUTO"
    )
    if gptresults.get("brand"):
        search=search.filter("term",manufacturer=gptresults["brand"].lower())
    if gptresults.get("category"):
        search=search.filter("term",category=gptresults["category"].lower())
    if gptresults.get("price_max"):
        try:
           price_max=float(gptresults["price_max"])
           search=search.filter("range",price={"lte":price_max})
        except ValueError:
            pass
    if gptresults.get("features"):
        for feature in gptresults["features"]:
            search=search.filter("term",features=feature.lower())
    if gptresults.get("material"):
        search=search.filter("term",material=gptresults["material"].lower())
    if gptresults.get("name"):
        search=search.filter("term",name=gptresults["name"].lower())
    results = search.execute()  
    product_ids = [int(hit.meta.id) for hit in results] 
    
    return Product.objects.filter(id__in=product_ids)

def store(request,category_id=None):
    if request.user.is_authenticated:
        customer=request.user.store_customer
        order,created=Order.objects.get_or_create(customer=customer,complete=False)
        items=order.orderitem_set.all() # type: ignore
        carttotal=order.get_cart_items
    else:
        cookiedata=cookiecart(request)
        carttotal=cookiedata['carttotal']
        order=cookiedata['order']
        items=cookiedata['items']
    search_query=request.GET.get('q')
    if search_query:
        products=search_results(search_query)
        category=None
    else:
        if category_id:
          category = get_object_or_404(Category,pk=category_id)
          products = Product.objects.filter(category=category)
        else:
            products = Product.objects.all()
            category = None
    context = {'products': products,'category':category,'carttotal':carttotal,'items':items,'order':order}
    return render(request, 'store/store.html', context)
def homepage(request):
     if request.user.is_authenticated:
         customer=request.user.store_customer
         order,created=Order.objects.get_or_create(customer=customer,complete=False)
         carttotal=order.get_cart_items
     else:
         cart = json.loads(request.COOKIES.get('cart', '{}'))
         carttotal = sum([item['quantity'] for item in cart.values()])
         
     categories=Category.objects.all()
     context={'categories':categories,'carttotal':carttotal}
     return render(request,'store/home.html',context)
def product_detail(request, pk):
    product = get_object_or_404(Product, id=pk)

    if request.user.is_authenticated:
        customer = request.user.store_customer
        order, created = Order.objects.get_or_create(customer=customer, complete=False)
        carttotal = order.get_cart_items
    else:
        cookiedata = cookiecart(request)
        carttotal = cookiedata['carttotal']

    context = {
        'product': product,
        'carttotal': carttotal,
    }
    return render(request, 'store/product.html', context)
def cart(request):
    if request.user.is_authenticated:
        customer = request.user.store_customer
        order, created = Order.objects.get_or_create(customer=customer, complete=False)
        items = order.orderitem_set.all() # type: ignore
        carttotal = order.get_cart_items
    else:
        cookiedata = cookiecart(request) 
        carttotal = cookiedata['carttotal']
        order = cookiedata['order']
        items = cookiedata['items']

    context = {'items': items, 'order': order, 'carttotal': carttotal}
    return render(request, 'store/cart.html', context)


def checkout(request):
    if request.user.is_authenticated:
        customer = request.user.store_customer
        order, created = Order.objects.get_or_create(customer=customer, complete=False)
        items = order.orderitem_set.all() # type: ignore
        carttotal = order.get_cart_items
    else:
        cookiedata = cookiecart(request)
        carttotal = cookiedata['carttotal']
        order = cookiedata['order']
        items = cookiedata['items']

    context = {'items': items, 'order': order, 'carttotal': carttotal}
    return render(request, 'store/checkout.html', context)

def updateItem(request):
    data = json.loads(request.body)
    print(data)
    productid = data['productid']
    action = data['action']
    size = data.get('size', 'M')
    customer = request.user.store_customer
    product = Product.objects.get(id=productid)
    order, created = Order.objects.get_or_create(customer=customer, complete=False)
    orderitem, created = Orderitem.objects.get_or_create(order=order, product=product,size=size)

    if action == 'add':
        orderitem.quantity += 1 # type: ignore
    elif action == 'remove':
        orderitem.quantity -= 1 # type: ignore
    
    if orderitem.quantity<=0: # type: ignore
         orderitem.delete()
         itemprice='$ 0'
         itemquantity=0
    else:
         orderitem.save()
         itemprice='$'+str(orderitem.quantity*orderitem.product.price) # type: ignore
         itemquantity = orderitem.quantity

    cartItems = order.get_cart_items
    cartTotal = '$'+ str(order.get_cart_total)
    return JsonResponse({
        'cartItems': cartItems,
        'cartTotal': cartTotal,
        'itemprice':itemprice,
        'itemquantity':itemquantity,
    })

def loginview(request):
    if request.method == 'GET':
        form = AuthenticationForm()
        return render(request, 'store/login.html', {'form': form})

    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username')
            password = data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return JsonResponse({'message': 'Login successful'}, status=200)
            else:
                return JsonResponse({'error': 'Invalid username or password'}, status=401)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

    return JsonResponse({'error': 'Only GET and POST methods allowed'}, status=405)

from django.shortcuts import render, redirect
from .forms import CustomUserCreationForm

def signupview(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')  
    else:
        form = CustomUserCreationForm()
    return render(request, 'store/signup.html', {'form': form})
def profileview(request):
    user=request.user
    customer=request.user.store_customer
    alladdress=Shippingaddress.objects.filter(customer=customer)
    context={'user':user,'addresses':alladdress}
    return render(request,'store/profile.html',context)
def myorders(request):
    customer = request.user.store_customer
    totalorders = Order.objects.filter(customer=customer, complete=True) 
    orders = [] 

    for order in totalorders:
        items = Orderitem.objects.filter(order=order)  
        item = {
            'Transaction_id': order.transaction_id,
            'date_ordered': order.date_ordered,
            'total_items': order.get_cart_items,
            'total_amount': order.get_cart_total,
            'items': [] 
        }
        for i in items:
            item['items'].append({
                'name': i.product.name, # type: ignore
                'price': i.product.price, # type: ignore
                'size': i.size,
                'quantity': i.quantity,
                'total_price': i.get_total
            })
        orders.append(item)  
    context = {'orders': orders}
    return render(request, 'store/myorders.html', context)
def search_suggestions(request):
    query = request.GET.get("q", "")
    if not query:
        return JsonResponse({'suggestions': []})

    search = ProductDocument.search()
    search = search.suggest(
        'product_suggest',
        query,
        completion={'field': 'name_suggest', 'size': 5}
    )
    response = search.execute()

    suggestions = [option.text for option in response.suggest.product_suggest[0].options]

    return JsonResponse({'suggestions': suggestions})

face_color_map = {
    "light": ["pastel blue", "lavender", "white"],
    "fair": ["peach", "sky blue", "grey"],
    "medium": ["navy", "emerald", "mustard"],
    "tan": ["olive", "maroon", "mustard"],
    "brown": ["teal", "beige", "orange"]
}
def upload_photo(request):
    if request.method == "POST":
        photo = request.FILES["photo"]
        path = "media/uploads/" + photo.name
        with open(path, "wb+") as f:
            for chunk in photo.chunks():
                f.write(chunk)
        result = detect_face_color(path)  # type: ignore
        category = result["category"]
        recommendations = face_color_map.get(category, [])
        products = Product.objects.filter(colour__in=recommendations)
        if request.user.is_authenticated:
          customer=request.user.store_customer 
          order,created=Order.objects.get_or_create(customer=customer,complete=False)
          items=order.orderitem_set.all() # type: ignore
          carttotal=order.get_cart_items
        else:
          cookiedata=cookiecart(request)
          carttotal=cookiedata['carttotal']
          order=cookiedata['order']
          items=cookiedata['items']
        context = {'products': products,'category':category,'carttotal':carttotal,'items':items,'order':order}
        return render(request, 'store/store.html', context)
    return render(request, 'store/upload_photo.html')


