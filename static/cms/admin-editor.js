/*
 * Запуск визуального редактора в админке.
 *
 * Настройки приходят из Python в атрибуте data-jodit, чтобы не держать
 * их в двух местах. Инициализация идёт и для блоков, добавленных на
 * странице кнопкой «Добавить ещё один»: Django создаёт их копированием
 * скрытой заготовки уже после загрузки страницы.
 */
(function () {
    "use strict";

    var READY = "data-ns3-ready";

    /* Разметка колонок. Сетка, а не таблица: так колонки сами встают
       друг под друга на телефоне — правило есть в стилях витрины. */
    function columnsHtml(count) {
        var cells = "";
        for (var i = 0; i < count; i += 1) {
            cells +=
                '<div class="cms-col"><p>Колонка ' + (i + 1) + "</p></div>";
        }
        return '<div class="cms-cols cms-cols-' + count + '">' + cells + "</div>";
    }

    function registerColumnsButton() {
        if (typeof Jodit === "undefined" || Jodit.ns3ColumnsReady) {
            return;
        }
        Jodit.ns3ColumnsReady = true;

        Jodit.defaultOptions.controls.ns3Columns = {
            name: "ns3Columns",
            tooltip: "Колонки",
            icon: "table",
            list: { 2: "Две колонки", 3: "Три колонки", 4: "Четыре колонки" },
            exec: function (editor, _current, options) {
                var count = parseInt(options.control.args &&
                    options.control.args[0], 10);
                if (!count) {
                    count = 2;
                }
                editor.s.insertHTML(columnsHtml(count));
            },
        };
    }

    function start(area) {
        if (area.getAttribute(READY) || typeof Jodit === "undefined") {
            return;
        }
        /* Заготовка инлайна Django — не настоящее поле, его трогать нельзя:
           иначе редактор появится в скрытой строке и сломает нумерацию. */
        if (area.id && area.id.indexOf("__prefix__") !== -1) {
            return;
        }

        var options;
        try {
            options = JSON.parse(area.getAttribute("data-jodit") || "{}");
        } catch (error) {
            options = {};
        }

        var csrf = document.querySelector("[name=csrfmiddlewaretoken]");
        if (csrf && options.uploader) {
            options.uploader.headers = { "X-CSRFToken": csrf.value };
        }

        area.setAttribute(READY, "1");
        registerColumnsButton();
        Jodit.make(area, options);
    }

    function startAll(root) {
        var nodes = (root || document).querySelectorAll("textarea.ns3-rich");
        Array.prototype.forEach.call(nodes, start);
    }

    document.addEventListener("DOMContentLoaded", function () {
        startAll(document);

        /* Инлайны добавляются уже после загрузки страницы. Следим за
           появлением новых полей вместо того, чтобы завязываться на
           внутренние события админки — они менялись от версии к версии. */
        if (typeof MutationObserver === "undefined") {
            return;
        }
        new MutationObserver(function (records) {
            records.forEach(function (record) {
                Array.prototype.forEach.call(record.addedNodes, function (node) {
                    if (node.nodeType !== 1) {
                        return;
                    }
                    if (node.matches && node.matches("textarea.ns3-rich")) {
                        start(node);
                    } else if (node.querySelectorAll) {
                        startAll(node);
                    }
                });
            });
        }).observe(document.body, { childList: true, subtree: true });
    });
})();
