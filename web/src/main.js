import Sortable from "sortablejs";
import * as api from "./api";
import "./style.css";
// ═══════════════════════════════════════════════════════════════════════════
// STATE
// ═══════════════════════════════════════════════════════════════════════════
let board;
let _dragging = false;
const COL_COLOURS = {
    "To Do": "#0ea5e9",
    "In Progress": "#a855f7",
    Review: "#f59e0b",
    Done: "#22c55e",
    "Blocked/Waiting": "#ef4444",
};
// ═══════════════════════════════════════════════════════════════════════════
// BOOT
// ═══════════════════════════════════════════════════════════════════════════
async function init() {
    board = await api.fetchBoard();
    render();
}
// ═══════════════════════════════════════════════════════════════════════════
// RENDER
// ═══════════════════════════════════════════════════════════════════════════
function render() {
    const app = document.getElementById("app");
    app.innerHTML = "";
    // ── Header ──
    const header = el("header", "board-header");
    header.innerHTML = `
    <h1>📋 Kanban Board</h1>
    <span class="board-subtitle">board.kanban.md</span>
  `;
    app.appendChild(header);
    // ── Columns ──
    const boardEl = el("div", "board");
    for (const column of board.columns) {
        boardEl.appendChild(renderColumn(column));
    }
    app.appendChild(boardEl);
}
function renderColumn(column) {
    const colour = COL_COLOURS[column.name] || "#64748b";
    const colEl = el("div", "column");
    colEl.dataset.column = column.name;
    colEl.style.setProperty("--col-accent", colour);
    // ── Header ──
    const headerEl = el("div", "column-header");
    headerEl.innerHTML = `
    <span class="column-dot" style="background:${colour}"></span>
    <span class="column-name">${esc(column.name)}</span>
    <span class="column-count">${column.cards.length}</span>
  `;
    colEl.appendChild(headerEl);
    // ── Card list ──
    const cardsEl = el("div", "cards");
    cardsEl.dataset.column = column.name;
    for (let i = 0; i < column.cards.length; i++) {
        cardsEl.appendChild(renderCard(column.cards[i], column.name, i));
    }
    colEl.appendChild(cardsEl);
    // ── Add-card button ──
    const addBtn = el("button", "add-card-btn");
    addBtn.textContent = "+ Add card";
    addBtn.addEventListener("click", () => openModal(column.name));
    colEl.appendChild(addBtn);
    // ── Drag-and-drop ──
    Sortable.create(cardsEl, {
        group: "kanban",
        draggable: ".card",
        handle: ".card-handle",
        animation: 200,
        easing: "cubic-bezier(0.22, 1, 0.36, 1)",
        ghostClass: "card-ghost",
        dragClass: "card-dragging",
        chosenClass: "card-chosen",
        forceFallback: true,
        fallbackClass: "card-fallback",
        fallbackOnBody: true,
        fallbackTolerance: 3,
        onStart: () => { _dragging = true; },
        onEnd: (evt) => {
            handleDrop(evt);
            // Suppress the click that fires after mouseup from a drag
            setTimeout(() => { _dragging = false; }, 50);
        },
    });
    return colEl;
}
function renderCard(card, colName, index) {
    const cardEl = el("div", "card");
    cardEl.dataset.column = colName;
    cardEl.dataset.index = String(index);
    // Top row (title + drag handle)
    const topEl = el("div", "card-top");
    const titleEl = el("div", "card-title");
    titleEl.textContent = card.title;
    topEl.appendChild(titleEl);
    const handleEl = el("button", "card-handle");
    handleEl.type = "button";
    handleEl.title = "Drag card";
    handleEl.ariaLabel = "Drag card";
    handleEl.textContent = "⋮⋮";
    handleEl.addEventListener("click", (e) => e.stopPropagation());
    topEl.appendChild(handleEl);
    cardEl.appendChild(topEl);
    // Due badge
    if (card.meta.due) {
        const badge = el("span", "card-due");
        const due = new Date(card.meta.due + "T00:00:00");
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const diff = Math.ceil((due.getTime() - today.getTime()) / 86400000);
        badge.textContent = formatDate(card.meta.due);
        if (diff < 0)
            badge.classList.add("overdue");
        else if (diff <= 2)
            badge.classList.add("soon");
        else if (diff <= 7)
            badge.classList.add("upcoming");
        cardEl.appendChild(badge);
    }
    // Body preview
    if (card.body) {
        const bodyEl = el("div", "card-body-preview");
        const lines = card.body.split("\n").filter((l) => l.trim());
        bodyEl.textContent =
            lines.length <= 2
                ? lines.join(" · ")
                : lines.slice(0, 2).join(" · ") + ` (+${lines.length - 2})`;
        cardEl.appendChild(bodyEl);
    }
    // Click → edit modal (suppressed during/after drag)
    cardEl.addEventListener("click", () => {
        if (_dragging)
            return;
        const liveCol = cardEl.dataset.column || colName;
        const liveIdx = Number(cardEl.dataset.index ?? String(index));
        openModal(liveCol, liveIdx);
    });
    return cardEl;
}
// ═══════════════════════════════════════════════════════════════════════════
// DRAG & DROP
// ═══════════════════════════════════════════════════════════════════════════
async function handleDrop(evt) {
    const fromCol = evt.from.dataset.column;
    const toCol = evt.to.dataset.column;
    const oldIdx = evt.oldIndex;
    const newIdx = evt.newIndex;
    if (fromCol === toCol && oldIdx === newIdx)
        return;
    try {
        board = await api.moveCard(fromCol, oldIdx, toCol, newIdx);
        // Don't full-rerender — DOM is already correct from SortableJS.
        // Just sync data-index attributes.
        syncIndices();
    }
    catch (err) {
        console.error("Move failed, re-rendering", err);
        board = await api.fetchBoard();
        render();
    }
}
/** After a drag-drop, update data-index and data-column attrs without full rerender. */
function syncIndices() {
    document.querySelectorAll(".cards").forEach((list) => {
        const colName = list.dataset.column;
        list.querySelectorAll(".card").forEach((card, i) => {
            card.dataset.index = String(i);
            card.dataset.column = colName;
        });
    });
}
// ═══════════════════════════════════════════════════════════════════════════
// MODAL  (add / edit / delete)
// ═══════════════════════════════════════════════════════════════════════════
function openModal(colName, cardIndex) {
    const isEdit = cardIndex !== undefined;
    const column = board.columns.find((c) => c.name === colName);
    const card = isEdit
        ? column.cards[cardIndex]
        : { title: "", meta: {}, body: "" };
    // ── Backdrop ──
    const backdrop = el("div", "modal-backdrop");
    backdrop.addEventListener("click", (e) => {
        if (e.target === backdrop)
            backdrop.remove();
    });
    // ── Modal shell ──
    const modal = el("div", "modal");
    // ── Title bar ──
    const titleBar = el("div", "modal-title-bar");
    titleBar.innerHTML = `
    <h2>${isEdit ? "Edit Card" : "New Card"}</h2>
    <button class="modal-close">&times;</button>
  `;
    titleBar.querySelector(".modal-close").addEventListener("click", () => backdrop.remove());
    modal.appendChild(titleBar);
    // ── Form ──
    const form = el("form", "modal-form");
    form.innerHTML = `
    <label>
      Title
      <input name="title" type="text" value="${attr(card.title)}" required autofocus />
    </label>
    <label>
      Due date
      <input name="due" type="date" value="${attr(card.meta.due || "")}" />
    </label>
    ${isEdit ? `
    <label>
      Column
      <select name="column">
        ${board.columns.map((c) => `<option value="${attr(c.name)}" ${c.name === colName ? "selected" : ""}>${esc(c.name)}</option>`).join("")}
      </select>
    </label>
    ` : ""}
    <label>
      Notes
      <textarea name="body" rows="6">${esc(card.body)}</textarea>
    </label>
  `;
    // ── Actions ──
    const actions = el("div", "modal-actions");
    if (isEdit) {
        const delBtn = el("button", "btn btn-danger");
        delBtn.type = "button";
        delBtn.textContent = "Delete";
        delBtn.addEventListener("click", async () => {
            if (!confirm(`Delete "${card.title}"?`))
                return;
            board = await api.deleteCard(colName, cardIndex);
            backdrop.remove();
            render();
        });
        actions.appendChild(delBtn);
    }
    const spacer = el("div", "spacer");
    actions.appendChild(spacer);
    const cancelBtn = el("button", "btn btn-secondary");
    cancelBtn.type = "button";
    cancelBtn.textContent = "Cancel";
    cancelBtn.addEventListener("click", () => backdrop.remove());
    actions.appendChild(cancelBtn);
    const saveBtn = el("button", "btn btn-primary");
    saveBtn.type = "submit";
    saveBtn.textContent = isEdit ? "Save" : "Add";
    actions.appendChild(saveBtn);
    form.appendChild(actions);
    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const fd = new FormData(form);
        const title = fd.get("title").trim();
        if (!title)
            return;
        const due = fd.get("due") || "";
        const body = fd.get("body").trim();
        const meta = { ...card.meta };
        if (due)
            meta.due = due;
        else
            delete meta.due;
        if (body && !meta.defaultExpanded)
            meta.defaultExpanded = "false";
        if (isEdit) {
            const newCol = fd.get("column") || colName;
            // If column changed, move first then edit
            if (newCol !== colName) {
                board = await api.moveCard(colName, cardIndex, newCol, 0);
                board = await api.editCard(newCol, 0, { title, meta, body });
            }
            else {
                board = await api.editCard(colName, cardIndex, { title, meta, body });
            }
        }
        else {
            board = await api.addCard(colName, title, meta, body);
        }
        backdrop.remove();
        render();
    });
    modal.appendChild(form);
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    // Focus the title input
    requestAnimationFrame(() => {
        form.querySelector('input[name="title"]')?.focus();
    });
}
// ═══════════════════════════════════════════════════════════════════════════
// UTILITIES
// ═══════════════════════════════════════════════════════════════════════════
function el(tag, className) {
    const e = document.createElement(tag);
    if (className)
        e.className = className;
    return e;
}
function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
}
function attr(s) {
    return s.replace(/"/g, "&quot;").replace(/</g, "&lt;");
}
function formatDate(iso) {
    const [y, m, d] = iso.split("-");
    return `${d}/${m}/${y}`;
}
// ═══════════════════════════════════════════════════════════════════════════
init();
