/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const NAV_ITEMS = [
    { label: "Dashboard", icon: "fa-dashboard", action: null },
    { label: "Books", icon: "fa-book", action: "library_manager.action_library_book" },
    { label: "Loans", icon: "fa-exchange", action: "library_manager.action_library_loan" },
    { label: "Ebooks", icon: "fa-tablet", action: "library_manager.action_library_ebook" },
    {
        label: "Categories",
        icon: "fa-tags",
        action: "library_manager.action_library_ebook_category",
    },
    {
        label: "Requests",
        icon: "fa-inbox",
        action: "library_manager.action_library_ebook_request",
    },
    {
        label: "Ebook Loans",
        icon: "fa-bookmark",
        action: "library_manager.action_library_ebook_loan",
    },
    {
        label: "Access",
        icon: "fa-key",
        action: "library_manager.action_library_ebook_access",
    },
    {
        label: "Reservations",
        icon: "fa-calendar",
        action: "library_manager.action_library_ebook_reservation",
    },
];

const LOAN_MODELS = [
    { model: "library.loan", state: "borrowed", relation: "book_id", kind: "Book" },
    {
        model: "library.ebook.loan",
        state: "active",
        relation: "ebook_id",
        kind: "eBook",
    },
];

function formatDate(date) {
    return [
        date.getFullYear(),
        String(date.getMonth() + 1).padStart(2, "0"),
        String(date.getDate()).padStart(2, "0"),
    ].join("-");
}

function getGroupCount(group) {
    return Number(group.__count || 0);
}

export class LibraryDashboard extends Component {
    static template = "library_manager.LibraryDashboard";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            error: null,
            navItems: NAV_ITEMS,
            stats: [],
            borrowers: [],
            months: [],
            topEbooks: [],
            loanRows: [],
            listTitle: "",
        });
        onWillStart(() => this.loadDashboard());
    }

    async loadDashboard() {
        this.state.loading = true;
        this.state.error = null;
        try {
            const today = new Date();
            const todayString = formatDate(today);
            const firstMonth = new Date(today.getFullYear(), today.getMonth() - 5, 1);
            const firstMonthString = formatDate(firstMonth);
            const nextMonthString = formatDate(
                new Date(today.getFullYear(), today.getMonth() + 1, 1)
            );
            const activeDomains = [
                [["state", "=", "borrowed"]],
                [["state", "=", "active"]],
            ];
            const overdueDomains = [
                [["state", "=", "borrowed"], ["due_date", "<", todayString]],
                [["state", "=", "active"], ["due_date", "<", todayString]],
            ];
            const monthDomain = (field) => [
                [field, ">=", firstMonthString],
                [field, "<", nextMonthString],
            ];
            const readMonths = (model) =>
                this.orm.readGroup(
                    model,
                    monthDomain("borrow_date"),
                    [],
                    ["borrow_date:month"],
                    { lazy: false }
                );

            const [
                ebookCount,
                physicalOpen,
                ebookOpen,
                physicalOverdue,
                ebookOverdue,
                requests,
                reservations,
                physicalBorrowers,
                ebookBorrowers,
                physicalMonths,
                ebookMonths,
                topGroups,
            ] = await Promise.all([
                this.orm.searchCount("library.ebook", [["active", "=", true]]),
                this.orm.searchCount("library.loan", activeDomains[0]),
                this.orm.searchCount("library.ebook.loan", activeDomains[1]),
                this.orm.searchCount("library.loan", overdueDomains[0]),
                this.orm.searchCount("library.ebook.loan", overdueDomains[1]),
                this.orm.searchCount("library.ebook.request", [["state", "=", "pending"]]),
                this.orm.searchCount("library.ebook.reservation", [["state", "=", "pending"]]),
                this.orm.readGroup(
                    "library.loan",
                    activeDomains[0],
                    ["borrower_id"],
                    ["borrower_id"],
                    { lazy: false }
                ),
                this.orm.readGroup(
                    "library.ebook.loan",
                    activeDomains[1],
                    ["borrower_id"],
                    ["borrower_id"],
                    { lazy: false }
                ),
                readMonths("library.loan"),
                readMonths("library.ebook.loan"),
                this.orm.readGroup(
                    "library.ebook.loan",
                    [],
                    ["ebook_id"],
                    ["ebook_id"],
                    { lazy: false }
                ),
            ]);

            const borrowerMap = new Map();
            for (const group of [...physicalBorrowers, ...ebookBorrowers]) {
                if (group.borrower_id) {
                    borrowerMap.set(group.borrower_id[0], group.borrower_id[1]);
                }
            }
            this.state.borrowers = [...borrowerMap.keys()];

            const monthCounts = new Map();
            for (const [model, groups] of [
                ["library.loan", physicalMonths],
                ["library.ebook.loan", ebookMonths],
            ]) {
                for (const group of groups) {
                    const range = group.__range?.["borrow_date:month"];
                    if (range?.from) {
                        const monthKey = range.from.slice(0, 7);
                        monthCounts.set(monthKey, (monthCounts.get(monthKey) || 0) + getGroupCount(group));
                    }
                }
            }
            this.state.months = Array.from({ length: 6 }, (_, index) => {
                const month = new Date(today.getFullYear(), today.getMonth() - 5 + index, 1);
                const key = formatDate(month).slice(0, 7);
                return {
                    key,
                    label: new Intl.DateTimeFormat(undefined, { month: "short" }).format(month),
                    count: monthCounts.get(key) || 0,
                };
            });

            this.state.topEbooks = topGroups
                .filter((group) => group.ebook_id)
                .sort((left, right) => getGroupCount(right) - getGroupCount(left))
                .slice(0, 5)
                .map((group) => ({
                    id: group.ebook_id[0],
                    name: group.ebook_id[1],
                    count: getGroupCount(group),
                }));

            this.state.stats = [
                {
                    label: "Total eBooks",
                    value: ebookCount,
                    icon: "fa-tablet",
                    tone: "blue",
                    kind: "ebooks",
                },
                {
                    label: "Active Borrowers",
                    value: borrowerMap.size,
                    icon: "fa-users",
                    tone: "purple",
                    kind: "borrowers",
                },
                {
                    label: "Open Loans",
                    value: physicalOpen + ebookOpen,
                    icon: "fa-exchange",
                    tone: "teal",
                    kind: "open",
                },
                {
                    label: "Overdue Loans",
                    value: physicalOverdue + ebookOverdue,
                    icon: "fa-clock-o",
                    tone: "red",
                    kind: "overdue",
                },
                {
                    label: "Pending Requests",
                    value: requests,
                    icon: "fa-inbox",
                    tone: "orange",
                    kind: "requests",
                },
                {
                    label: "Active Reservations",
                    value: reservations,
                    icon: "fa-calendar",
                    tone: "green",
                    kind: "reservations",
                },
            ];
        } catch (error) {
            this.state.error = error.message || String(error);
        } finally {
            this.state.loading = false;
        }
    }

    navigate(item) {
        if (item.action) {
            this.action.doAction(item.action);
        }
    }

    async openStat(stat) {
        const actionByKind = {
            ebooks: [
                "library.ebook",
                [["active", "=", true]],
                "eBooks",
            ],
            borrowers: [
                "res.partner",
                [["id", "in", this.state.borrowers]],
                "Active Borrowers",
            ],
            requests: [
                "library.ebook.request",
                [["state", "=", "pending"]],
                "Pending eBook Requests",
            ],
            reservations: [
                "library.ebook.reservation",
                [["state", "=", "pending"]],
                "Active Reservations",
            ],
        };
        if (stat.kind === "open" || stat.kind === "overdue") {
            await this.openLoanList(stat.kind);
            return;
        }
        const [model, domain, name] = actionByKind[stat.kind];
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: model,
            views: [[false, "list"], [false, "form"]],
            domain,
            target: "current",
        });
    }

    async openLoanList(kind) {
        this.state.loading = true;
        this.state.error = null;
        this.state.listTitle = kind === "overdue" ? "Overdue Loans" : "Open Loans";
        try {
            const today = formatDate(new Date());
            const rowsByModel = await Promise.all(
                LOAN_MODELS.map(async ({ model, state, relation, kind: type }) => {
                    const domain = [["state", "=", state]];
                    if (kind === "overdue") {
                        domain.push(["due_date", "<", today]);
                    }
                    const records = await this.orm.searchRead(
                        model,
                        domain,
                        [relation, "borrower_id", "borrow_date", "due_date", "state"]
                    );
                    return records.map((record) => ({
                        id: record.id,
                        model,
                        title: record[relation]?.[1] || "",
                        borrower: record.borrower_id?.[1] || "",
                        borrowDate: record.borrow_date,
                        dueDate: record.due_date,
                        kind: type,
                    }));
                })
            );
            this.state.loanRows = rowsByModel.flat().sort((left, right) =>
                right.borrowDate.localeCompare(left.borrowDate)
            );
        } catch (error) {
            this.state.error = error.message || String(error);
        } finally {
            this.state.loading = false;
        }
    }

    openLoan(row) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: row.model,
            res_id: row.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openEbookLoans(ebookId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "eBook Loan History",
            res_model: "library.ebook.loan",
            views: [[false, "list"], [false, "form"]],
            domain: [["ebook_id", "=", ebookId]],
            target: "current",
        });
    }

    get chartMax() {
        return Math.max(1, ...this.state.months.map((month) => month.count));
    }
}

registry.category("actions").add("library_manager.library_dashboard", LibraryDashboard);
