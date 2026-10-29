/**
 * LionFlow AI — Calendrier visuel des campagnes.
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    const container = document.getElementById("campaignCalendar");
    const loader = document.getElementById("calendarLoader");

    if (!container || typeof FullCalendar === "undefined") {
      return;
    }

    // ---- i18n (fallback FR si non injecté) ----
    const I18N = window.LF_I18N || {};
    const T = {
      btn_today: (I18N.calendar && I18N.calendar.btn_today) || "Aujourd’hui",
      btn_month: (I18N.calendar && I18N.calendar.btn_month) || "Mois",
      btn_week: (I18N.calendar && I18N.calendar.btn_week) || "Semaine",
      btn_day: (I18N.calendar && I18N.calendar.btn_day) || "Jour",
      btn_list: (I18N.calendar && I18N.calendar.btn_list) || "Liste",
      rescheduled_success:
        (I18N.calendar && I18N.calendar.rescheduled_success) ||
        "Campagne replanifiée",
      reschedule_failed:
        (I18N.calendar && I18N.calendar.reschedule_failed) ||
        "Replanification impossible",
      load_failed:
        (I18N.calendar && I18N.calendar.load_failed) ||
        "Impossible de charger les campagnes",
      network_error:
        (I18N.calendar && I18N.calendar.network_error) || "Erreur réseau",
    };
    const STATUS_LABELS = I18N.status || {};
    const LOCALE = (I18N.locale || "fr").slice(0, 2);

    const csrfToken =
      (document.querySelector('meta[name="csrf-token"]') || {}).content ||
      (document.querySelector('input[name="csrf_token"]') || {}).value ||
      "";

    const eventsUrl = container.dataset.eventsUrl;
    const rescheduleUrlTemplate = container.dataset.rescheduleUrlTemplate;
    const statusFilter = document.getElementById("calendarStatusFilter");

    // Construit l'URL de replanification pour un id donné.
    function buildRescheduleUrl(id) {
      return rescheduleUrlTemplate.replace(
        /\/0(\/reschedule)$/,
        "/" + id + "$1",
      );
    }

    function showToast(message, isError) {
      if (window.LionFlow && typeof window.LionFlow.toast === "function") {
        window.LionFlow.toast(message, isError ? "error" : "success");
        return;
      }
      if (isError) {
        console.error(message);
      } else {
        console.log(message);
      }
    }

    function statusLabel(status) {
      return STATUS_LABELS[status] || status || "";
    }

    // ✅ AFFICHE LE LOADER IMMÉDIATEMENT AU CHARGEMENT DE LA PAGE
    if (loader) {
      loader.style.setProperty("display", "flex", "important");
    }

    const calendar = new FullCalendar.Calendar(container, {
      initialView: "dayGridMonth",
      locale: LOCALE,
      firstDay: 1,
      height: "auto",
      nowIndicator: true,
      dayMaxEvents: 4,
      weekNumbers: false,
      headerToolbar: {
        left: "prev,next today",
        center: "title",
        right: "dayGridMonth,timeGridWeek,timeGridDay,listWeek",
      },
      buttonText: {
        today: T.btn_today,
        month: T.btn_month,
        week: T.btn_week,
        day: T.btn_day,
        list: T.btn_list,
      },
      editable: true,
      eventStartEditable: true,
      eventDurationEditable: false,
      selectable: false,

      // ✅ GESTION DU LOADER
      loading: function (isLoading) {
        if (!loader) return;
        if (isLoading) {
          loader.style.setProperty("display", "flex", "important");
        } else {
          loader.style.setProperty("display", "none", "important");
        }
      },

      // Chargement des événements depuis l'API
      events: function (info, successCallback, failureCallback) {
        const params = new URLSearchParams({
          start: info.startStr,
          end: info.endStr,
        });
        if (statusFilter && statusFilter.value) {
          params.append("statuses", statusFilter.value);
        }

        fetch(eventsUrl + "?" + params.toString(), {
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        })
          .then(function (response) {
            if (!response.ok) {
              throw new Error("HTTP " + response.status);
            }
            return response.json();
          })
          .then(successCallback)
          .catch(function (err) {
            console.error("[calendar] Erreur chargement événements:", err);
            showToast(T.load_failed, true);
            failureCallback(err);
          });
      },

      // Clic sur un événement → redirection
      eventClick: function (info) {
        const url = info.event.extendedProps && info.event.extendedProps.url;
        if (url) {
          info.jsEvent.preventDefault();
          window.location.href = url;
        }
      },

      // Drag & drop → replanification
      eventDrop: function (info) {
        if (!info.event.start) {
          info.revert();
          return;
        }

        const id = info.event.id;
        const isoStart = info.event.start.toISOString();
        const url = buildRescheduleUrl(id);

        fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
            "X-CSRFToken": csrfToken,
          },
          credentials: "same-origin",
          body: JSON.stringify({ start: isoStart }),
        })
          .then(function (response) {
            return response
              .json()
              .catch(function () {
                return {};
              })
              .then(function (data) {
                return { ok: response.ok, data: data };
              });
          })
          .then(function (result) {
            if (!result.ok) {
              showToast(
                (result.data && result.data.error) || T.reschedule_failed,
                true,
              );
              info.revert();
            } else {
              showToast(T.rescheduled_success, false);
            }
          })
          .catch(function (err) {
            console.error("[calendar] Erreur replanification:", err);
            showToast(T.network_error, true);
            info.revert();
          });
      },

      // Infobulle native + classes CSS personnalisées
      eventDidMount: function (info) {
        const props = info.event.extendedProps || {};
        const lines = [info.event.title];
        if (props.status) {
          lines.push("• " + statusLabel(props.status));
        }
        if (props.total_contacts != null) {
          lines.push("• " + props.total_contacts + " contacts");
        }
        info.el.setAttribute("title", lines.join("\n"));
        info.el.classList.add("lf-calendar-event");
      },
    });

    calendar.render();

    // Filtre statut → recharge les événements
    if (statusFilter) {
      statusFilter.addEventListener("change", function () {
        calendar.refetchEvents();
      });
    }
  });
})();
