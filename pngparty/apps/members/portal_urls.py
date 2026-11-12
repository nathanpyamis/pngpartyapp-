from django.urls import path

from .views import batch_cards_pdf, single_card_pdf

urlpatterns = [
    path("<uuid:member_id>/card.pdf", single_card_pdf, name="member_card_single"),
    path("cards.pdf", batch_cards_pdf, name="member_cards_batch"),
]
