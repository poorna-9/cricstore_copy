

from .models import Order

def cart_data(request):
    if request.user.is_authenticated:
        customer = request.user.store_customer
        order, created = Order.objects.get_or_create(customer=customer, complete=False)
    else:
        order = {'get_cart_items': 0, 'get_cart_total': 0}
    return {'order': order}
