from django.shortcuts import render

# Create your views here.
# =======================================================================
# atelier: 彩花のアトリエページ
# =======================================================================
def atelier(request):
    return render(request, "atelier.html")

