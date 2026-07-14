# ================================================================================
# urls.pyで定義したviewsを実装するためのファイル
# ===============================================================================
from django.shortcuts import render

def index(request):
    return render(request, 'index.html')