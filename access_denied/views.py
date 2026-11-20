from django.shortcuts import render

# Create your views here.
def access_denied(request):
    return render (request, "403.html")