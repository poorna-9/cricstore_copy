def cookiecart(request):
    import json
    from .models import Product

    try:
        raw_cookie = request.COOKIES.get('cart', '{}')
        cart = json.loads(raw_cookie)
    except Exception as e:
        cart = {}

    items = []
    order = {'get_cart_items': 0, 'get_cart_total': 0, 'shipping': False}
    carttotal = 0

    for key in cart:
        try:
            product_id = int(key.split('_')[0])  
            quantity = cart[key]['quantity']
            size = cart[key].get('size', 'M')
            product = Product.objects.get(id=product_id)

            total = product.price * quantity
            carttotal += quantity
            order['get_cart_total'] += total
            order['get_cart_items'] += quantity

            item = {
                'product': {
                    'id': product.id,
                    'name': product.name,
                    'price': product.price,
                    'imageURL': product.imageURL,
                },
                'quantity': quantity,
                'get_total': total,
                'size': size,
            }
            items.append(item)

            if not product.digital:
                order['shipping'] = True

        except Exception as e:
            print(f" Error with key '{key}': {e}")


    return {'items': items, 'order': order, 'carttotal': carttotal}



