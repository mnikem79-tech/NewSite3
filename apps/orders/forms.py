"""Форма оформления заказа."""

import re

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.payments.models import PaymentMethod
from apps.shipping.models import ShippingMethod

PHONE_RE = re.compile(r"^\+?[\d\s\-()]{7,20}$")


class CheckoutForm(forms.Form):
    customer_name = forms.CharField(
        label=_("Имя и фамилия"),
        max_length=255,
        widget=forms.TextInput(attrs={"autocomplete": "name"}),
    )
    email = forms.EmailField(
        label=_("E-mail"),
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
        help_text=_("На него придёт подтверждение заказа."),
    )
    phone = forms.CharField(
        label=_("Телефон"),
        max_length=32,
        widget=forms.TextInput(attrs={"autocomplete": "tel", "placeholder": "+7 900 000-00-00"}),
    )

    shipping_method = forms.ModelChoiceField(
        label=_("Способ доставки"),
        queryset=ShippingMethod.objects.none(),
        empty_label=None,
        widget=forms.RadioSelect,
    )
    shipping_address = forms.CharField(
        label=_("Адрес доставки"),
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Город, улица, дом, квартира, индекс"}
        ),
    )

    payment_method = forms.ModelChoiceField(
        label=_("Способ оплаты"),
        queryset=PaymentMethod.objects.none(),
        empty_label=None,
        widget=forms.RadioSelect,
    )

    comment = forms.CharField(
        label=_("Комментарий к заказу"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Списки читаются при создании формы, а не при импорте модуля:
        # иначе отключённый в админке способ доставки продолжал бы
        # предлагаться до перезапуска сервера.
        self.fields["shipping_method"].queryset = ShippingMethod.objects.active()
        self.fields["payment_method"].queryset = PaymentMethod.objects.active()

        for field in self.fields.values():
            widget = field.widget
            if not isinstance(widget, forms.RadioSelect):
                widget.attrs.setdefault("class", "form-control")

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if not PHONE_RE.match(phone):
            raise forms.ValidationError(_("Введите телефон в формате +7 900 000-00-00."))
        return phone

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get("shipping_method")
        address = (cleaned.get("shipping_address") or "").strip()

        # Адрес обязателен только там, где он нужен: для самовывоза его
        # требовать бессмысленно.
        if method and method.requires_address and not address:
            self.add_error("shipping_address", _("Укажите адрес доставки."))

        cleaned["shipping_address"] = address
        return cleaned
