"""Masaüstü arayüzünün sunum katmanı.

Bu paketteki her şey saf sunumdur: motoru tanımaz, iş parçacığı başlatmaz,
ağa çıkmaz. İş mantığı `gui.py` içinde kalır. Sınır bilinçlidir — sayfa
kurulumu handler'larına sıkı bağlı olduğu için orada durur, yeniden
kullanılabilir görsel parçalar ise buraya iner.

* `theme`   — renk, boyut, yarıçap belirteçleri (Tk gerektirmez)
* `icons`   — mantıksal ikon adı -> glyph eşlemesi (Tk gerektirmez)
* `fonts`   — gömülü TTF'leri süreç-özel yükler, CTkFont üretir
* `widgets` — tasarımdaki bileşen primitifleri
"""
