# FinController — AI Finance Reconciliation Platform (Hackathon Edition) 🚀

[![Razorpay Theme](https://img.shields.io/badge/Theme-Razorpay%20Navy%20%26%20Blue-146EB4)](https://razorpay.com)
[![Python](https://img.shields.io/badge/Backend-Python%20%7C%20Flask-3776AB)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## 📌 Problem Statement
Finance operations teams face a critical challenge closing the loop between merchant e-commerce orders, **Razorpay payment ledger rows**, and **bank settlement credits**. Manual 3-way reconciliation is slow, error-prone, and struggles with:
- Amount mismatches (fee/tax deductions)
- Delayed bank payouts (T+3 settlement gaps)
- Missing bank credits / Ghost entries
- Duplicate bank settlement credits
- Payment ID typos & fuzzy reference matches

## 💡 The Solution
**FinController** is an automated **AI-Powered 3-Way Reconciliation System** engineered to reconcile payments across Orders, Razorpay, and Bank statements. It quantifies operational match rates, evaluates precision/recall against ground truth, and features **Autonomous AI Resolution Agents** to take action on open exceptions.

---

## 🔥 Key Hackathon Upgrades & Features

### ⚡ 1. Live Webhook & Event Stream Simulator
- Ingest real-time webhook event streams (`payment.captured`, `order.paid`, `settlement.processed`).
- Fire 4 live scenario simulation events directly from the dashboard:
  - ⚡ **Fire Clean Match**: Instant 3-way auto-reconciliation.
  - ⚠️ **Fire Missing Settlement**: Flag missing bank payouts.
  - ⚖️ **Fire Amount Mismatch**: Ingest ₹500 discrepancy.
  - 📋 **Fire Duplicate Credit**: Flag duplicate bank settlement rows.

### 🔑 2. Razorpay Live REST API Integration
- Direct integration with Razorpay REST APIs (`https://api.razorpay.com/v1/payments`).
- Connect live using your **Razorpay Key ID & Key Secret** or test with the built-in **Live Mock API Sandbox**.

### 📁 3. Drag-and-Drop Bank Statement Ingestion
- Drag & drop custom `.csv`, `.xls`, or `.xlsx` bank settlement files directly onto the UI dropzone for instant automated reconciliation.
- **Included Sample Test Statements**:
  - `successful_bank_statement.csv`: Test file containing 100% clean settlement matches.
  - `sample_custom_bank_statement.csv`: Test file containing custom transactions and edge-case exceptions.

### 🤖 4. Autonomous AI Action Agent
For unresolved exceptions, FinBot doesn't just explain the issue—it takes action:
- 🎫 **Auto-Draft Razorpay Support Tickets**: Generates formatted merchant tickets requesting UTR traces.
- 🚨 **Generate Slack Ops Alerts**: Generates formatted team notifications for high-risk exceptions.

---

## 🛠️ System Architecture

```
 ┌──────────────────────┐
 │ Merchant E-Commerce  │ ──► Webhook (Order Created / Paid) ──┐
 │      Orders          │                                      │
 └──────────────────────┘                                      │
                                                               ▼
 ┌──────────────────────┐                              ┌───────────────┐
 │   Razorpay API       │ ──► Webhook (payment.captured) ──►  FinController│
 │  (Live Gateway)      │ ──► REST API (Fetch Payments)  ────► Data Pipeline │
 └──────────────────────┘                                      └───────┬───────┘
                                                                       │
 ┌──────────────────────┐                                              │
 │ Bank Account / SFTP  │ ──► Bank Statement Ingestion ────────────────┘
 │ (HDFC/ICICI Payouts) │     (CSV / Excel Dropzone)
 └──────────────────────┘
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
Ensure you have **Python 3.9+** installed.

### 2. Installation
Clone the repository and install dependencies:
```bash
git clone https://github.com/YOUR_USERNAME/FinController.git
cd FinController
pip install -r requirements.txt
```

### 3. Generate Synthetic Ground-Truth Data
```bash
python generate_data.py
```

### 4. Run Unit Tests
```bash
python -m unittest discover tests
```

### 5. Launch Application
```bash
python server.py
```
Open **`http://127.0.0.1:5000`** in your web browser!

---

## 🔑 Environment Variables (Optional)

You can set your Razorpay API credentials in environment variables or enter them directly in the UI modal:

```powershell
$env:RAZORPAY_KEY_ID="rzp_test_YOUR_KEY_ID"
$env:RAZORPAY_KEY_SECRET="YOUR_KEY_SECRET"
python server.py
```

---

## 🏆 Metrics & Benchmarks

| Metric | Benchmark Value | Description |
| --- | ---: | --- |
| **Total Records Processed** | 60 | Initial synthetic batch size |
| **Match Rate** | 73.33% | Operational coverage |
| **Precision** | 100.00% | 0 false matches (no incorrect auto-closures) |
| **Recall** | 100.00% | 100% of matchable payments found |
| **F1 Score** | 100.00% | Balanced accuracy score |
| **Processing Speed** | ~1,500 rec/sec | High-speed multi-pass reconciliation engine |

---

## 📜 License
Licensed under the [MIT License](LICENSE).
