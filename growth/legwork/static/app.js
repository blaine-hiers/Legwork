/* app.js — Demo Generator.

   Every node here is built with UI.el. Nothing concatenates markup into
   innerHTML: this page renders a prospect's own pasted email straight back onto
   the screen, which is exactly the shape of input where string-built markup
   stops being a style question. */

(function () {
  "use strict";

  var el = UI.el, $ = UI.$, api = UI.api;

  var S = {
    lib: null,          // /api/state — starters, handling, patterns, demos
    sheet: null,        // the open sheet
    analysis: null,
    view: "work",
    sample: ""          // the starter's sample text, for the Use the sample button
  };

  var LAST = "demogen.last";

  // ------------------------------------------------------------ plumbing

  /* The sheet object graph is built once, by `open`, and lives until another
     sheet is opened. Nothing else is allowed to replace it.

     That is a rule, not an implementation detail. Every field on the screen is
     wired straight to the step object it edits — `oninput: function () {
     step[key] = ...; }` — so the handlers hold references *into* this graph.
     `S.sheet = r.sheet` in the save handler swapped in a freshly deserialised
     copy whose steps were new objects, and from that moment every keystroke
     updated an orphan: the input showed the new number, the sheet that got
     saved and analysed did not. One edit per sheet-opening was kept and every
     one after it went nowhere, with no error. Calling `paintSteps()` after
     each save would re-point the handlers, but it rebuilds the inputs under
     the person typing into them and takes the focus and the caret with it —
     in the one conversation this app exists for. So the response is merged in
     instead.

     Only the half of it the server owns, though. What is on the screen was
     typed more recently than the copy that came back, and may have been typed
     while the request was still in flight, so adopting `steps` or `client`
     from the response would undo live typing — the same data loss by a longer
     route. Bookkeeping the server assigns (stamps, version, which starter it
     came from) is the part the screen has no opinion about, and it is taken by
     exclusion so a field added to the document later lands here by default. */
  var TYPED = { name: 1, client: 1, industry: 1, notes: 1, hourly_cost: 1, steps: 1 };

  function adoptSaved(saved) {
    // A reply about the sheet that was open two clicks ago must not be written
    // into the one that is open now.
    if (!saved || !S.sheet || saved.id !== S.sheet.id) return false;
    Object.keys(saved).forEach(function (key) {
      if (!TYPED[key]) S.sheet[key] = saved[key];
    });
    return true;
  }

  var save;                 // built in boot, where the status pill exists

  function doSave() {
    if (!S.sheet || !S.sheet.id) return Promise.resolve();
    return api.put("/api/sheets/" + encodeURIComponent(S.sheet.id), S.sheet)
      .then(function (r) { if (adoptSaved(r.sheet)) paintAnalysis(r.analysis); });
  }

  /* Recompute is separate from save on purpose. The numbers are what the owner
     is watching while you type, and making them wait on a write to disk puts a
     visible stutter in the one moment the app exists for. */
  var recompute = UI.debounce(function () {
    if (!S.sheet) return;
    // Stamp the sheet id this request was issued for. /api/analyze echoes
    // back no id of its own to check against, unlike the save reply
    // adoptSaved guards above — so the id has to be captured here, at issue
    // time, and compared against whatever is open when the reply lands.
    var issuedFor = S.sheet.id;
    api.post("/api/analyze", S.sheet)
      .then(function (r) {
        if (S.sheet && S.sheet.id === issuedFor) paintAnalysis(r.analysis);
      })
      .catch(function () { /* the sheet is still on screen; a failed sum is not fatal */ });
  }, 220);

  function touched() { save(); recompute(); }

  // ------------------------------------------------------------- sidebar

  function paintSheets() {
    var host = $("#sheetList");
    UI.clear(host);
    var sheets = (S.lib && S.lib.sheets) || [];
    $("#sheetsEmpty").classList.toggle("hidden", sheets.length > 0);
    sheets.forEach(function (s) {
      var row = el("div", {
        class: "list-item" + (S.sheet && s.id === S.sheet.id ? " active" : ""),
        onclick: function () { open(s.id); }
      }, [
        el("span", { class: "t" }, [
          el("strong", { text: s.client || s.name }),
          el("small", { text: (s.client ? s.name + " · " : "") + UI.pluralize(s.steps, "step") })
        ]),
        el("button", {
          class: "btn icon sm ghost", title: "Delete this sheet",
          onclick: function (e) { e.stopPropagation(); remove(s); }
        }, ["×"])
      ]);
      host.appendChild(row);
    });
  }

  function remove(s) {
    UI.confirmDanger("Delete this sheet?", (s.client || s.name) +
      " — the sheet goes, and there is no other copy of it.", function () {
      UI.guard(api.del("/api/sheets/" + encodeURIComponent(s.id)), "Delete")
        .then(function () {
          if (S.sheet && S.sheet.id === s.id) { S.sheet = null; S.analysis = null; paintSheet(); }
          return refreshSheets();
        })
        .catch(function (e) {
        // Only swallow the rejection guard() already toasted. Anything else
        // is a real bug in the .then() chain above and must keep surfacing
        // as an unhandled rejection, the way it would with no catch at all.
        if (!e || !e.uiGuardToasted) throw e;
      });
    });
  }

  function refreshSheets() {
    return api.get("/api/sheets").then(function (r) {
      S.lib.sheets = r.sheets; paintSheets();
    });
  }

  // ---------------------------------------------------------- open / new

  function open(id) {
    // Flush whatever the debounce is still holding for the sheet that is
    // open right now, before it gets replaced below. Safe to do only because
    // adoptSaved (above) drops a reply whose id no longer matches S.sheet by
    // the time it lands — otherwise this flush's own late reply could win a
    // race against the sheet being opened here.
    save.now();
    return UI.guard(api.get("/api/sheets/" + encodeURIComponent(id)), "Open")
      .then(function (r) {
        S.sheet = r.sheet;
        S.sample = "";
        save.idle();        // it came off disk: the pill says so before any typing
        try { localStorage.setItem(LAST, id); } catch (e) {}
        paintSheet();
        paintAnalysis(r.analysis);
        paintSheets();
        // A starter carries the sample text and the question to ask; a saved
        // sheet does not, so fetch it back rather than storing a second copy.
        if (S.sheet.starter) {
          api.get("/api/starters/" + encodeURIComponent(S.sheet.starter))
            .then(function (st) {
              S.sample = st.starter.sample || "";
              paintAsk(st.starter.asks);
            })
            .catch(function () {});
        } else {
          paintAsk("");
        }
      })
      .catch(function (e) {
        // Only swallow the rejection guard() already toasted. Anything else
        // is a real bug in the .then() chain above and must keep surfacing
        // as an unhandled rejection, the way it would with no catch at all.
        if (!e || !e.uiGuardToasted) throw e;
      });
  }

  function paintAsk(text) {
    var box = $("#askLine");
    UI.clear(box);
    box.classList.toggle("hidden", !text);
    if (!text) return;
    box.appendChild(el("b", { text: "Ask them: " }));
    box.appendChild(document.createTextNode(text));
  }

  function newSheet() {
    var wrap = el("div", {}, []);
    wrap.appendChild(el("p", { class: "muted small",
      text: "Pick the closest one. Everything in it is a starting guess — change " +
            "the numbers as they talk, and the sheet will say what is still unanswered." }));
    // A starter file that would not load is shown here rather than logged.
    (S.lib.starter_problems || []).forEach(function (p) {
      wrap.appendChild(el("div", { class: "cannot",
        text: p.file + " — " + p.why }));
    });
    (S.lib.starters || []).forEach(function (st) {
      wrap.appendChild(el("div", { class: "list-item", onclick: function () {
        m.close(); create(st.key);
      } }, [
        el("span", { class: "t" }, [
          el("strong", { text: st.title }),
          el("small", { text: st.industry + " · " + st.blurb })
        ])
      ]));
    });
    wrap.appendChild(el("div", { class: "sep" }, []));
    wrap.appendChild(el("button", { class: "btn block", onclick: function () {
      m.close(); create("");
    } }, ["Start from nothing"]));
    var m = UI.modal({ title: "What are they in?", body: wrap });
  }

  function create(starter) {
    UI.guard(api.post("/api/sheets", starter ? { starter: starter } : {}), "New sheet")
      .then(function (r) {
        return refreshSheets().then(function () { return open(r.sheet.id); });
      })
      .catch(function (e) {
        // Only swallow the rejection guard() already toasted. Anything else
        // is a real bug in the .then() chain above and must keep surfacing
        // as an unhandled rejection, the way it would with no catch at all.
        if (!e || !e.uiGuardToasted) throw e;
      });
  }

  // ---------------------------------------------------------- the fields

  function bindField(sel, key, asNumber) {
    var node = $(sel);
    node.addEventListener("input", function () {
      if (!S.sheet) return;
      S.sheet[key] = asNumber ? (parseFloat(node.value) || 0) : node.value;
      touched();
    });
  }

  function paintSheet() {
    var has = !!S.sheet;
    $("#noSheet").classList.toggle("hidden", has);
    $("#sheetBody").classList.toggle("hidden", !has);
    if (!has) return;
    $("#fClient").value = S.sheet.client || "";
    $("#fIndustry").value = S.sheet.industry || "";
    $("#fName").value = S.sheet.name || "";
    $("#fRate").value = S.sheet.hourly_cost ? S.sheet.hourly_cost : "";
    paintSteps();
  }

  // ----------------------------------------------------------- the steps

  function paintSteps() {
    var host = $("#steps");
    UI.clear(host);
    var steps = S.sheet.steps || [];
    $("#stepCount").textContent = UI.pluralize(steps.length, "step");
    steps.forEach(function (step, i) { host.appendChild(stepCard(step, i)); });
  }

  function numField(label, step, key, hint) {
    var input = el("input", {
      type: "number", min: "0", step: "1", inputmode: "decimal",
      value: step[key] || "",
      oninput: function () { step[key] = parseFloat(input.value) || 0; touched(); }
    }, []);
    return el("div", { class: "field" }, [
      el("label", { text: label }), input,
      hint ? el("div", { class: "hint", text: hint }) : null
    ]);
  }

  function textField(label, step, key, placeholder) {
    var input = el("input", {
      type: "text", value: step[key] || "", placeholder: placeholder || "",
      oninput: function () { step[key] = input.value; touched(); }
    }, []);
    return el("div", { class: "field" }, [el("label", { text: label }), input]);
  }

  function stepCard(step, index) {
    var card = el("div", { class: "step", dataset: { id: step.id } }, []);

    var title = el("input", {
      class: "title", type: "text", value: step.name || "",
      placeholder: "What happens here",
      oninput: function () { step.name = title.value; touched(); }
    }, []);

    card.appendChild(el("div", { class: "head" }, [
      title,
      el("button", { class: "btn icon sm ghost", title: "Move up",
        onclick: function () { move(index, -1); } }, ["↑"]),
      el("button", { class: "btn icon sm ghost", title: "Move down",
        onclick: function () { move(index, 1); } }, ["↓"]),
      el("button", { class: "btn icon sm ghost", title: "Remove this step",
        onclick: function () { removeStep(index); } }, ["×"])
    ]));

    card.appendChild(el("div", { class: "nums" }, [
      textField("Who does it", step, "who", "Office, tech, owner"),
      textField("Where", step, "system", "The software, paper, email"),
      numField("Minutes each time", step, "minutes"),
      numField("How often a month", step, "runs_per_month", "Ask out loud")
    ]));

    var opts = el("div", { class: "opts" }, []);
    (S.lib.handling || []).forEach(function (h) {
      var box = el("input", {
        type: "checkbox", checked: (step.handling || []).indexOf(h.key) !== -1,
        onchange: function () {
          var list = step.handling || (step.handling = []);
          var at = list.indexOf(h.key);
          if (box.checked && at === -1) list.push(h.key);
          if (!box.checked && at !== -1) list.splice(at, 1);
          touched();
        }
      }, []);
      opts.appendChild(el("label", { class: "opt" }, [
        box,
        el("span", {}, [
          document.createTextNode(h.label),
          el("span", { class: "h", text: h.hint })
        ])
      ]));
    });

    card.appendChild(el("div", { class: "handling" }, [
      el("div", { class: "lbl", text: "What happens to the information" }), opts
    ]));

    card.appendChild(el("div", { class: "result", dataset: { for: step.id } }, [
      el("span", { class: "none", text: "…" })
    ]));
    return card;
  }

  function move(index, by) {
    var steps = S.sheet.steps, to = index + by;
    if (to < 0 || to >= steps.length) return;
    var it = steps.splice(index, 1)[0];
    steps.splice(to, 0, it);
    paintSteps(); touched();
  }

  function removeStep(index) {
    var gone = S.sheet.steps.splice(index, 1)[0];
    paintSteps(); touched();
    UI.toast("Step removed", "", 7000, { label: "Undo", onClick: function () {
      S.sheet.steps.splice(index, 0, gone); paintSteps(); touched();
    } });
  }

  function addStep() {
    S.sheet.steps = S.sheet.steps || [];
    S.sheet.steps.push({
      id: "s" + (S.sheet.steps.length + 1) + "-" + Math.floor(Date.now() % 100000),
      name: "", who: "", system: "", minutes: 0, runs_per_month: 0, handling: [], note: ""
    });
    paintSteps(); touched();
    var cards = UI.$$("#steps .step");
    var last = cards[cards.length - 1];
    if (last) last.querySelector("input.title").focus();
  }

  // ------------------------------------------------------- the numbers

  function band(low, high) { return low + "–" + high + " hrs/mo"; }

  function paintAnalysis(a) {
    if (!a) return;
    S.analysis = a;

    var t = a.totals;
    var host = $("#totals");
    UI.clear(host);
    host.appendChild(el("div", { class: "big-band", text: band(t.saved_low, t.saved_high) }));
    host.appendChild(el("div", { class: "sub-band",
      text: t.share_low + "%–" + t.share_high + "% of the hand-time described" }));
    host.appendChild(el("div", { class: "workline",
      text: UI.pluralize(t.steps, "step") + " · " + t.hours_month + " hrs a month of hand-time today" }));
    host.appendChild(el("div", { class: "arith", text: t.how }));
    host.appendChild(el("div", { class: "arith",
      text: "Hand-time coming off the work — not a person freed up and not money " +
            "in the bank. Two steps done by the same person do not free two people." }));

    var r = $("#byRole");
    UI.clear(r);
    if (!a.by_role || !a.by_role.length) {
      r.appendChild(el("span", { text: "Nothing described yet." }));
    } else {
      a.by_role.forEach(function (role) {
        r.appendChild(el("div", { class: "workline",
          text: role.who + ": " + role.hours_text + " hrs/mo (" + role.share + "%)" }));
        r.appendChild(el("div", { class: "arith",
          text: role.money_how || role.rate_how || role.addressable }));
      });
    }

    var f = $("#firstOut");
    UI.clear(f);
    if (a.first) {
      f.appendChild(el("div", {}, [el("strong", { text: a.first.name })]));
      f.appendChild(el("div", { class: "workline", text: band(a.first.saved_low, a.first.saved_high) }));
      f.appendChild(el("div", { class: "arith", text: a.first.priority_how }));
      if (a.first.money_how) f.appendChild(el("div", { class: "arith", text: a.first.money_how }));
    } else {
      f.appendChild(el("span", { text: "Nothing ticked yet." }));
    }

    var w = $("#warnings");
    UI.clear(w);
    if (!a.warnings.length) {
      w.appendChild(el("span", { text: "Nothing outstanding." }));
    } else {
      var ul = el("ul", {}, []);
      a.warnings.forEach(function (line) { ul.appendChild(el("li", { text: line })); });
      w.appendChild(ul);
    }

    paintStepResults(a);
    if (S.view === "sheet") loadOnePager();
  }

  function paintStepResults(a) {
    var firstId = a.first && a.first.id;
    a.steps.forEach(function (r) {
      var card = document.querySelector('#steps .step[data-id="' + cssEsc(r.id) + '"]');
      if (!card) return;
      card.classList.toggle("first", r.id === firstId);
      var box = card.querySelector(".result");
      UI.clear(box);
      if (!r.patterns.length) {
        box.appendChild(el("span", { class: "none",
          text: "Nothing ticked — this is on the sheet as work, with no saving claimed." }));
        return;
      }
      // The percentages sit next to the hours because hours round: a two-minute
      // step shows 0.0–0.0, and the band is what stops that reading as a single
      // figure on a screen the owner is looking at.
      box.appendChild(el("span", { class: "band", text: band(r.saved_low, r.saved_high) }));
      box.appendChild(el("span", { class: "muted small",
        text: "  (" + r.share_low + "%–" + r.share_high + "% of this step)" }));
      box.appendChild(el("div", { class: "how", text: r.saved_how }));
      r.patterns.forEach(function (p) {
        box.appendChild(el("div", { class: "pat" }, [
          el("b", { text: p.title }),
          el("div", { class: "line", text: p.becomes }),
          el("div", { class: "how", text: p.how }),
          el("div", { class: "line", text: "Needs: " + p.needs }),
          el("div", { class: "line", text: "Why the range is wide: " + p.why })
        ]));
      });
    });
  }

  /* Step ids come off the wire. They are generated here and by the importer, but
     a sheet edited by hand or arriving from a future map could carry a quote. */
  function cssEsc(s) {
    return (window.CSS && CSS.escape) ? CSS.escape(String(s))
                                      : String(s).replace(/["\\\]]/g, "\\$&");
  }

  // -------------------------------------------------------- the live demo

  function paintDemoPicker() {
    var pick = $("#demoPick");
    UI.clear(pick);
    (S.lib.demos || []).forEach(function (d) {
      pick.appendChild(el("option", { value: d.key, text: d.title }, []));
    });
    var docs = $("#docPick");
    UI.clear(docs);
    (S.lib.documents || []).forEach(function (name) {
      docs.appendChild(el("option", { value: name, text: name.replace(/-/g, " ") }, []));
    });
    pick.addEventListener("change", demoModeChanged);
    demoModeChanged();
  }

  function demoModeChanged() {
    var key = $("#demoPick").value;
    var d = (S.lib.demos || []).filter(function (x) { return x.key === key; })[0];
    $("#demoBlurb").textContent = d ? d.blurb : "";
    $("#docPickWrap").classList.toggle("hidden", key !== "document");
    $("#chaseWrap").classList.toggle("hidden", key !== "chase");
    $("#pasteWrap").classList.toggle("hidden", key === "chase");
    var runnable = ["intake", "document", "chase", "checklist"].indexOf(key) !== -1;
    $("#btnRunDemo").classList.toggle("is-disabled", !runnable);
    if (!runnable) {
      UI.clear($("#demoOut"));
      $("#demoOut").appendChild(el("div", { class: "card muted small", text:
        d ? d.blurb : "" }, []));
    }
  }

  function parseChase(text) {
    return String(text || "").split("\n").map(function (line) {
      if (!line.trim()) return null;   // a blank line, not a finding
      var bits = line.split(",");
      if (bits.length < 2) {
        // No comma to split on. Sent through anyway, with no due date, so
        // the backend lists it under "Dates it could not read" instead of
        // it vanishing before the count is even taken.
        return { who: line.trim(), what: "", due: "" };
      }
      return {
        who: (bits[0] || "").trim(),
        what: (bits.slice(1, bits.length - 1).join(",") || "").trim(),
        due: (bits[bits.length - 1] || "").trim()
      };
    }).filter(Boolean);
  }

  function runDemo() {
    var key = $("#demoPick").value;
    var payload = {};
    if (key === "chase") payload.rows = parseChase($("#chaseText").value);
    else payload.text = $("#demoText").value;
    if (key === "document") payload.template = $("#docPick").value;

    UI.guard(api.post("/api/demo/" + encodeURIComponent(key), payload), "Demo")
      .then(function (r) { paintDemo(key, r.result); })
      .catch(function (e) {
        // Only swallow the rejection guard() already toasted. Anything else
        // is a real bug in the .then() chain above and must keep surfacing
        // as an unhandled rejection, the way it would with no catch at all.
        if (!e || !e.uiGuardToasted) throw e;
      });
  }

  function paintDemo(key, res) {
    var host = $("#demoOut");
    UI.clear(host);
    $("#demoHow").textContent = res.how || "";

    if (key === "intake" || key === "checklist") {
      var card = el("div", { class: "card" }, [el("h1", { text: key === "intake"
        ? "What it pulled out" : "What it checked" })]);
      (res.found || res.passed || []).forEach(function (f) {
        card.appendChild(el("div", { class: "kv" }, [
          el("span", { class: "k", text: f.label }),
          el("span", { class: "v", text: f.value }),
          el("span", { class: "by", text: f.found_by || "" })
        ]));
      });
      host.appendChild(card);

      var gaps = res.missed || res.problems || [];
      var miss = el("div", { class: "card" }, [
        el("h1", { text: key === "intake" ? "What it did not find" : "What needs fixing" }),
        el("p", { class: "muted small", text:
          "Shown on purpose. A demo that only shows its wins gets believed once." })
      ]);
      if (!gaps.length) miss.appendChild(el("div", { class: "muted small", text: "Nothing." }));
      gaps.forEach(function (g) {
        miss.appendChild(el("div", { class: "kv gap" }, [
          el("span", { class: "k", text: g.label }),
          el("span", { class: "v", text: g.why || g.problem })
        ]));
      });
      if (res.cannot_catch) miss.appendChild(el("div", { class: "cannot", text: res.cannot_catch }));
      host.appendChild(miss);
      return;
    }

    if (key === "document") {
      host.appendChild(el("div", { class: "card" }, [
        el("h1", { text: "The draft" }),
        el("p", { class: "muted small", text:
          "Anything it could not fill says ask, in the text, where a person will see it." }),
        el("pre", { class: "doc", text: res.text })
      ]));
      return;
    }

    if (key === "chase") {
      var box = el("div", { class: "card" }, [
        el("h1", { text: res.late_count + " late" })
      ]);
      (res.rows || []).forEach(function (r) {
        box.appendChild(el("div", { class: "chaserow" }, [
          el("span", { class: "who", text: r.who }),
          el("span", { class: "what", text: r.what }),
          el("span", { class: "badge " + (r.days_late > 0 ? "bad" : (r.days_late === 0 ? "warn" : "")),
                       text: r.days_late > 0 ? r.days_late + "d late" : r.state })
        ]));
        if (r.message) box.appendChild(el("div", { class: "muted small", text: "→ " + r.message }));
      });
      host.appendChild(box);
      if ((res.unreadable || []).length) {
        var bad = el("div", { class: "card" }, [
          el("h1", { text: "Dates it could not read" }),
          el("p", { class: "muted small", text: "Listed, not skipped." })
        ]);
        res.unreadable.forEach(function (u) {
          bad.appendChild(el("div", { class: "kv gap" }, [
            el("span", { class: "k", text: u.who }),
            el("span", { class: "v", text: u.due + " — " + u.why })
          ]));
        });
        host.appendChild(bad);
      }
    }
  }

  // --------------------------------------------------------- the one-pager

  function loadOnePager() {
    if (!S.sheet) return;
    api.post("/api/export/text", S.sheet)
      .then(function (r) { $("#sheetOut").textContent = r.text; })
      .catch(function (e) { $("#sheetOut").textContent = "Could not build it: " + e.message; });
  }

  function download() {
    if (!S.sheet) return;
    UI.guard(api.post("/api/export/markdown", S.sheet), "Download")
      .then(function (r) { UI.download(r.filename, r.text, r.mime); })
      .catch(function (e) {
        // Only swallow the rejection guard() already toasted. Anything else
        // is a real bug in the .then() chain above and must keep surfacing
        // as an unhandled rejection, the way it would with no catch at all.
        if (!e || !e.uiGuardToasted) throw e;
      });
  }

  // -------------------------------------------------------------- import

  function importMap() {
    var input = el("input", { type: "file", accept: ".json,application/json" }, []);
    input.addEventListener("change", function () {
      var file = input.files && input.files[0];
      if (!file) return;
      var reader = new FileReader();
      reader.onload = function () {
        var parsed;
        try { parsed = JSON.parse(String(reader.result)); }
        catch (e) { UI.toast.bad("That file isn't readable JSON."); return; }
        UI.guard(api.post("/api/import/flowmap", { handoff: parsed, save: true }), "Import")
          .then(function (r) {
            return refreshSheets().then(function () { return open(r.sheet.id); });
          })
          .then(function () {
            UI.toast.warn("Times and names came across. What happens to the " +
              "information did not — a map never recorded it, so tick it as they talk.", 9000);
          })
          .catch(function (e) {
        // Only swallow the rejection guard() already toasted. Anything else
        // is a real bug in the .then() chain above and must keep surfacing
        // as an unhandled rejection, the way it would with no catch at all.
        if (!e || !e.uiGuardToasted) throw e;
      });
      };
      reader.readAsText(file);
    });
    input.click();
  }

  // --------------------------------------------------------------- views

  function show(view) {
    S.view = view;
    UI.$$(".tab").forEach(function (t) { t.classList.toggle("active", t.dataset.view === view); });
    $("#viewWork").classList.toggle("hidden", view !== "work");
    $("#viewDemo").classList.toggle("hidden", view !== "demo");
    $("#viewSheet").classList.toggle("hidden", view !== "sheet");
    if (view === "sheet") loadOnePager();
  }

  // ---------------------------------------------------------------- boot

  function boot() {
    $("#themeSlot").appendChild(UI.themeButton());

    // The pill in the header is the only place this app can say whether the
    // typing is safe. It was passed `null`, so the markup carried a status
    // element that nothing ever wrote to and the app said nothing either way.
    save = UI.autosave(doSave, $("#saveStatus"));

    $("#btnNew").addEventListener("click", newSheet);
    $("#btnAddStep").addEventListener("click", addStep);
    $("#btnImport").addEventListener("click", importMap);
    $("#btnRunDemo").addEventListener("click", runDemo);
    $("#btnDemo").addEventListener("click", function () { show("demo"); });
    $("#btnSheet").addEventListener("click", function () { show("sheet"); });
    $("#btnCopy").addEventListener("click", function () { UI.copy($("#sheetOut").textContent); });
    $("#btnDownload").addEventListener("click", download);
    $("#btnPrint").addEventListener("click", function () { window.print(); });
    $("#btnSample").addEventListener("click", function () {
      if (!S.sample) { UI.toast.warn("This sheet didn't come from a starter, so there's no sample."); return; }
      $("#demoText").value = S.sample;
    });
    UI.$$(".tab").forEach(function (t) {
      t.addEventListener("click", function () { show(t.dataset.view); });
    });

    bindField("#fClient", "client");
    bindField("#fIndustry", "industry");
    bindField("#fName", "name");
    bindField("#fRate", "hourly_cost", true);

    UI.hotkey("ctrl+d", function () { show("demo"); });
    UI.hotkey("ctrl+p", function () { show("sheet"); });

    // The last write must not die with the page. keepalive is what makes that
    // true — see the note on UI.autosave.
    window.addEventListener("beforeunload", function () { save.now(); });

    api.get("/api/state").then(function (lib) {
      S.lib = lib;
      paintSheets();
      paintDemoPicker();
      var last = null;
      try { last = localStorage.getItem(LAST); } catch (e) {}
      var known = (lib.sheets || []).some(function (s) { return s.id === last; });
      var next = known ? open(last) : Promise.resolve();
      return next.then(function () { UI.booted(); });
    }).catch(function (e) {
      UI.toast.bad("Could not start: " + e.message);
      UI.booted();   // report anyway — a silent blank page is worse than a bad one
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
