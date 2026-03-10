# finance_manager.py
# Made by CtrlAltSpace: https://github.com/CtrlAltSpace
# Copyright (C) 2026 CtrlAltSpace

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import sys
import ctypes
import sqlite3
import os
import random
import re
import html
from datetime import datetime, date, timedelta
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QDoubleSpinBox,
    QDateEdit, QMessageBox, QFrame, QGridLayout, QFormLayout,
    QProgressBar, QStackedWidget, QTextEdit, QScrollArea, QSizePolicy,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog,
    QDialogButtonBox, QSpinBox, QCheckBox, QAbstractScrollArea, QInputDialog
)
from PyQt6.QtCore import Qt, QDate, pyqtSignal, QSize, QTimer, QLocale, QUrl
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon, QPainter, QPen, QDesktopServices
import calendar

                                                               
class AppConstants:
    MIN_AMOUNT = 0.01
    MAX_AMOUNT = 999_999_999_999.99
    MAX_BUDGET_AMOUNT = 999_999_999_999.99
    DEFAULT_MONTHLY_INCOME = 3000.00
    DEFAULT_BUDGET_AMOUNT = 100.00
    DEFAULT_GOAL_TARGET = 50.00
    RECENT_TRANSACTION_LIMIT = 10
    MONTHLY_SUMMARY_LIMIT = 6
    NOTIFICATION_INTERVAL_MS = 60_000
    BUDGET_WARNING_THRESHOLD = 80
    BUDGET_OVER_THRESHOLD = 100
    BUDGET_REMAINING_WARNING_RATIO = 0.2
    PROGRESS_MIN = 0.0
    PROGRESS_MAX = 100.0
    GOAL_PROGRESS_HALF = 50
    GOAL_PROGRESS_ALMOST = 75
    SAVINGS_GUIDE_RATE = 0.2
    SAVINGS_PROJECTION_RATE = 0.05
    EXPENSE_BREAKDOWN_BAR_DIVISOR = 2.5
    EXPENSE_BREAKDOWN_BAR_MAX = 40
    LOADING_EASTER_EGG_CHANCE = 0.075


def resolve_app_icon():
    """Resolve icon path for source and PyInstaller one-file execution."""
    icon_name = "Finance Manager icon.ico"
    candidates = []

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidates.append(os.path.join(meipass, icon_name))
        candidates.append(os.path.join(os.path.dirname(sys.executable), icon_name))
    else:
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), icon_name))

    candidates.append(os.path.join(os.getcwd(), icon_name))

    for path in candidates:
        if path and os.path.exists(path):
            return QIcon(path)

    # Fallback: if frozen, the executable itself may carry the embedded icon.
    if getattr(sys, "frozen", False):
        return QIcon(sys.executable)

    return QIcon()


DEFAULT_CATEGORIES = [
    ('Salary', 'income', '#2ecc71', '💰'),
    ('Gift', 'income', '#2ecc71', '🎁'),
    ('Other Income', 'income', '#2ecc71', '💵'),
    ('Food', 'expense', '#e74c3c', '🍔'),
    ('Transport', 'expense', '#3498db', '🚗'),
    ('Entertainment', 'expense', '#9b59b6', '🎮'),
    ('Shopping', 'expense', '#f3ef12', '🛍️'),
    ('Bills', 'expense', '#34495e', '📋'),
    ('Healthcare', 'expense', '#e55512', '🏥'),
    ('Education', 'expense', '#1abc9c', '📚'),
    ('Charity', 'donation', '#e67e22', '❤️'),
    ('Helping Others', 'donation', '#e67e22', '🤝'),
    ('Community', 'donation', '#e67e22', '🌍')
]

DEFAULT_INCOME_CATEGORIES = [
    ('Salary', '#2ecc71', '💰'),
    ('Gift', '#2ecc71', '🎁'),
    ('Other Income', '#2ecc71', '💵')
]

DEFAULT_EXPENSE_CATEGORIES = [
    ('Food', '#e74c3c', '🍔'),
    ('Transport', '#3498db', '🚗'),
    ('Entertainment', '#9b59b6', '🎮'),
    ('Shopping', "#f3ef12", '🛍️'),
    ('Bills', '#34495e', '📋'),
    ('Healthcare', "#e55512", '🏥'),
    ('Education', '#1abc9c', '📚')
]

DEFAULT_DONATION_CATEGORIES = [
    ('Charity', '#e67e22', '❤️'),
    ('Helping Others', '#e67e22', '🤝'),
    ('Community', '#e67e22', '🌍')
]


def clamp_percentage(value):
    try:
        return max(AppConstants.PROGRESS_MIN, min(AppConstants.PROGRESS_MAX, float(value)))
    except (TypeError, ValueError):
        return AppConstants.PROGRESS_MIN


class DatabaseError(Exception):
    """Raised when database operations fail in a recoverable way."""


class AutoHeightTextEdit(QTextEdit):
    """QTextEdit that auto-resizes its height to fit content."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.document().contentsChanged.connect(self._defer_height_refresh)

    def _defer_height_refresh(self):
        QTimer.singleShot(0, self.refresh_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh_height()

    def refresh_height(self):
        if self.lineWrapMode() != QTextEdit.LineWrapMode.NoWrap:
            self.document().setTextWidth(max(0, self.viewport().width() - 4))
        doc_height = int(self.document().size().height())
        frame = self.frameWidth() * 2
        self.setFixedHeight(max(120, doc_height + frame + 16))


def db_guard(default_value):
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except DatabaseError:
                return default_value() if callable(default_value) else default_value
            except sqlite3.Error as e:
                self._log_db_error(func.__name__, e)
                return default_value() if callable(default_value) else default_value
        return wrapper
    return decorator

                                                            
class DatabaseManager:
    def __init__(self, db_path="finance_data.db"):
        self.db_path = db_path
        self.last_error = None
        try:
            self.init_database()
        except sqlite3.Error as e:
            self._log_db_error("init_database", e)
        except DatabaseError as e:
            self._log_db_error("init_database", e)
    
    def get_connection(self):
        """Get a new database connection"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA journal_mode=WAL")                                                     
            return conn
        except sqlite3.Error as e:
            self._log_db_error("connect", e)
            raise DatabaseError(str(e))

    def _log_db_error(self, action, error):
        self.last_error = f"{action}: {error}"
        print(f"Database error during {action}: {error}")
    
    def init_database(self):
        """Initialize database with required tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
                             
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY,
                starting_balance REAL DEFAULT 0,
                monthly_income REAL DEFAULT 0,
                show_splash_on_startup INTEGER DEFAULT 1,
                currency TEXT DEFAULT 'USD',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
                                                           
        cursor.execute("PRAGMA table_info(settings)")
        settings_columns = {row[1] for row in cursor.fetchall()}
        if "show_splash_on_startup" not in settings_columns:
            cursor.execute(
                "ALTER TABLE settings ADD COLUMN show_splash_on_startup INTEGER DEFAULT 1"
            )
        
                          
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT CHECK(type IN ('income', 'expense', 'donation')),
                color TEXT DEFAULT '#3498db',
                icon TEXT DEFAULT '📊',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(name, type)  -- Prevent duplicate category names within same type
            )
        ''')
        
                            
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY,
                type TEXT CHECK(type IN ('income', 'expense', 'donation')),
                amount REAL NOT NULL,
                category_id INTEGER,
                description TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES categories (id)
            )
        ''')
        
                              
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS donation_goals (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                target_amount REAL NOT NULL,
                current_amount REAL DEFAULT 0,
                deadline_date TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

                                                                     
        cursor.execute("PRAGMA table_info(donation_goals)")
        goal_columns = {row[1] for row in cursor.fetchall()}
        if "goal_type" not in goal_columns:
            cursor.execute(
                "ALTER TABLE donation_goals ADD COLUMN goal_type TEXT NOT NULL DEFAULT 'donation'"
            )
        
                       
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY,
                category_id INTEGER NOT NULL,
                monthly_limit REAL NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES categories (id),
                UNIQUE(category_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recurring_transactions (
                id INTEGER PRIMARY KEY,
                transaction_type TEXT CHECK(transaction_type IN ('income', 'expense', 'donation')),
                amount REAL NOT NULL,
                category_id INTEGER,
                description TEXT,
                interval_value INTEGER NOT NULL DEFAULT 1,
                interval_unit TEXT CHECK(interval_unit IN ('day', 'week', 'month')) NOT NULL DEFAULT 'month',
                next_run_date TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES categories (id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recurring_goal_saves (
                id INTEGER PRIMARY KEY,
                goal_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                interval_value INTEGER NOT NULL DEFAULT 1,
                interval_unit TEXT CHECK(interval_unit IN ('day', 'week', 'month')) NOT NULL DEFAULT 'month',
                next_run_date TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (goal_id) REFERENCES donation_goals (id)
            )
        ''')

                                                               
        cursor.execute("DELETE FROM categories WHERE name IN (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      ('Salary', 'Gift', 'Other Income', 'Food', 'Transport', 'Entertainment',
                       'Shopping', 'Bills', 'Healthcare', 'Education', 'Charity', 'Helping Others', 'Community'))
        
                                               
        
        cursor.executemany('''
            INSERT OR REPLACE INTO categories (name, type, color, icon)
            VALUES (?, ?, ?, ?)
        ''', DEFAULT_CATEGORIES)
        
                                               
        cursor.execute('''
            INSERT OR IGNORE INTO settings (id, starting_balance, monthly_income, currency)
            VALUES (1, 0, 0, 'USD')
        ''')
        
        conn.commit()
        conn.close()
    
    @db_guard(0)
    def get_current_balance(self):
        """Calculate and return current balance"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
                                  
            cursor.execute("SELECT starting_balance FROM settings WHERE id = 1")
            result = cursor.fetchone()
            starting_balance = result[0] if result else 0
            
                            
            cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'income'")
            total_income = cursor.fetchone()[0]
            
                                            
            cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type IN ('expense', 'donation')")
            total_outgoing = cursor.fetchone()[0]
            
            return starting_balance + total_income - total_outgoing
        finally:
            conn.close()
    
    @db_guard(0)
    def get_monthly_income(self):
        """Get monthly income from settings"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT monthly_income FROM settings WHERE id = 1")
            result = cursor.fetchone()
            monthly_income = result[0] if result else 0
            return monthly_income
        finally:
            conn.close()
    
    def set_monthly_income(self, income):
        """Set monthly income in settings"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE settings 
                SET monthly_income = ?
                WHERE id = 1
            ''', (income,))
            
            conn.commit()
            return True
        except sqlite3.Error as e:
            self._log_db_error("set_monthly_income", e)
            return False
        finally:
            conn.close()

    @db_guard(True)
    def should_show_splash_on_startup(self):
        """Return whether splash should be shown on app startup."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT show_splash_on_startup FROM settings WHERE id = 1")
            row = cursor.fetchone()
            return bool(row[0]) if row else True
        finally:
            conn.close()

    def set_show_splash_on_startup(self, enabled):
        """Persist splash visibility preference."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE settings SET show_splash_on_startup = ? WHERE id = 1",
                (1 if enabled else 0,)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            self._log_db_error("set_show_splash_on_startup", e)
            return False
        finally:
            conn.close()
    
    def add_transaction(self, transaction_type, amount, category_id=None, description=None):
        """Add a new transaction with balance check and budget notification"""
        try:
            if amount <= 0:
                return False, "Amount must be greater than zero."

                                                                  
            if transaction_type in ['expense', 'donation']:
                current_balance = self.get_current_balance()
                if amount > current_balance:
                    return False, "Insufficient funds"
            elif transaction_type == 'income':
                current_balance = self.get_current_balance()
                projected_balance = round(current_balance + amount, 2)
                max_balance = round(AppConstants.MAX_AMOUNT, 2)
                if projected_balance > max_balance:
                    return False, f"Total money cannot exceed ${max_balance:,.2f}"
            
            conn = self.get_connection()
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    INSERT INTO transactions (type, amount, category_id, description, date)
                    VALUES (?, ?, ?, ?, datetime('now'))
                ''', (transaction_type, amount, category_id, description))
                
                                                             
                if transaction_type == 'donation':
                    self.update_donation_goals(amount, conn)
                
                conn.commit()
                return True, "Transaction added successfully"
                
            except sqlite3.Error as e:
                conn.rollback()
                self._log_db_error("add_transaction", e)
                return False, "Database error while saving transaction."
            finally:
                conn.close()
                
        except Exception as e:
            return False, f"Error: {e}"
    
    @db_guard(list)
    def get_categories(self, category_type=None):
        """Get categories, optionally filtered by type"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            if category_type:
                cursor.execute('''
                    SELECT id, name, color, icon FROM categories 
                    WHERE type = ? ORDER BY name
                ''', (category_type,))
            else:
                cursor.execute('''
                    SELECT id, name, type, color, icon FROM categories 
                    ORDER BY type, name
                ''')
            
            categories = []
            for row in cursor.fetchall():
                if category_type:
                    categories.append({
                        'id': row[0],
                        'name': row[1],
                        'color': row[2],
                        'icon': row[3]
                    })
                else:
                    categories.append({
                        'id': row[0],
                        'name': row[1],
                        'type': row[2],
                        'color': row[3],
                        'icon': row[4]
                    })
            
            return categories
        finally:
            conn.close()
    
    @db_guard(lambda: {
        'total_income': 0,
        'total_expenses': 0,
        'total_donations': 0,
        'recent_transactions': []
    })
    def get_summary_stats(self):
        """Get summary statistics"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
                        
            cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'income'")
            total_income = cursor.fetchone()[0]
            
            cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'expense'")
            total_expenses = cursor.fetchone()[0]
            
            cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'donation'")
            total_donations = cursor.fetchone()[0]
            
                                     
            cursor.execute('''
                SELECT t.type, t.amount, c.name, c.icon, t.description, t.date
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.id
                ORDER BY t.date DESC LIMIT ?
            ''', (AppConstants.RECENT_TRANSACTION_LIMIT,))
            recent = cursor.fetchall()
            
            return {
                'total_income': total_income,
                'total_expenses': total_expenses,
                'total_donations': total_donations,
                'recent_transactions': recent
            }
        finally:
            conn.close()

    @db_guard(list)
    def get_all_transactions(self):
        """Get all transactions ordered by most recent first."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT t.type, t.amount, c.name, c.icon, t.description, t.date
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.id
                ORDER BY t.date DESC
            ''')
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def _next_recurring_date(from_date, interval_value, interval_unit):
        base_date = datetime.strptime(from_date, "%Y-%m-%d").date()
        interval_value = max(1, int(interval_value))
        if interval_unit == 'day':
            next_date = base_date + timedelta(days=interval_value)
        elif interval_unit == 'week':
            next_date = base_date + timedelta(weeks=interval_value)
        else:
            month = base_date.month - 1 + interval_value
            year = base_date.year + month // 12
            month = month % 12 + 1
            day = min(base_date.day, calendar.monthrange(year, month)[1])
            next_date = date(year, month, day)
        return next_date.isoformat()

    def add_recurring_transaction(self, transaction_type, amount, category_id, description, start_date, interval_value, interval_unit):
        """Create recurring transaction schedule."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            interval_value = max(1, int(interval_value))
            today = date.today().isoformat()
                                                                                       
                                                                                      
            next_run_date = (
                self._next_recurring_date(start_date, interval_value, interval_unit)
                if start_date <= today else start_date
            )
            cursor.execute('''
                INSERT INTO recurring_transactions (
                    transaction_type, amount, category_id, description,
                    interval_value, interval_unit, next_run_date, is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ''', (
                transaction_type, amount, category_id, description,
                interval_value, interval_unit, next_run_date
            ))
            conn.commit()
            return True
        except sqlite3.Error as e:
            self._log_db_error("add_recurring_transaction", e)
            return False
        finally:
            conn.close()

    def add_recurring_goal_save(self, goal_id, amount, start_date, interval_value, interval_unit):
        """Create recurring auto-save schedule for a goal."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO recurring_goal_saves (
                    goal_id, amount, interval_value, interval_unit, next_run_date, is_active
                )
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (goal_id, amount, max(1, int(interval_value)), interval_unit, start_date))
            conn.commit()
            return True
        except sqlite3.Error as e:
            self._log_db_error("add_recurring_goal_save", e)
            return False
        finally:
            conn.close()

    def process_recurring_items(self):
        """Process all due recurring transactions and goal auto-saves."""
        today = date.today().isoformat()

        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT id, transaction_type, amount, category_id, description, interval_value, interval_unit, next_run_date
                FROM recurring_transactions
                WHERE is_active = 1 AND next_run_date <= ?
                ORDER BY next_run_date
            ''', (today,))
            recurring_txns = cursor.fetchall()
        finally:
            conn.close()

        for rec_id, transaction_type, amount, category_id, description, interval_value, interval_unit, next_run_date in recurring_txns:
            success, _ = self.add_transaction(transaction_type, amount, category_id, description)
            if not success:
                continue
            new_next = self._next_recurring_date(next_run_date, interval_value, interval_unit)
            conn = self.get_connection()
            cur = conn.cursor()
            try:
                cur.execute('UPDATE recurring_transactions SET next_run_date = ? WHERE id = ?', (new_next, rec_id))
                conn.commit()
            finally:
                conn.close()

        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT id, goal_id, amount, interval_value, interval_unit, next_run_date
                FROM recurring_goal_saves
                WHERE is_active = 1 AND next_run_date <= ?
                ORDER BY next_run_date
            ''', (today,))
            recurring_goal_saves = cursor.fetchall()
        finally:
            conn.close()

        for rec_id, goal_id, amount, interval_value, interval_unit, next_run_date in recurring_goal_saves:
            success, _ = self.contribute_to_goal(goal_id, amount)
            if not success:
                continue

            conn = self.get_connection()
            cur = conn.cursor()
            try:
                cur.execute('SELECT is_active FROM donation_goals WHERE id = ?', (goal_id,))
                row = cur.fetchone()
                goal_still_active = bool(row and row[0] == 1)
                if goal_still_active:
                    new_next = self._next_recurring_date(next_run_date, interval_value, interval_unit)
                    cur.execute('UPDATE recurring_goal_saves SET next_run_date = ? WHERE id = ?', (new_next, rec_id))
                else:
                    cur.execute('UPDATE recurring_goal_saves SET is_active = 0 WHERE id = ?', (rec_id,))
                conn.commit()
            finally:
                conn.close()

    @db_guard(list)
    def get_upcoming_recurring_items(self, limit=6):
        """Return upcoming recurring transactions and goal saves sorted by date."""
        limit = max(1, int(limit))
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                '''
                SELECT
                    rt.next_run_date AS run_date,
                    'transaction' AS item_type,
                    rt.transaction_type AS subtype,
                    rt.amount AS amount,
                    COALESCE(c.icon, '') AS icon,
                    COALESCE(c.name, 'Uncategorized') AS name
                FROM recurring_transactions rt
                LEFT JOIN categories c ON c.id = rt.category_id
                WHERE rt.is_active = 1
                UNION ALL
                SELECT
                    rgs.next_run_date AS run_date,
                    'goal_save' AS item_type,
                    COALESCE(g.goal_type, 'goal') AS subtype,
                    rgs.amount AS amount,
                    '🎯' AS icon,
                    COALESCE(g.name, 'Goal Auto-save') AS name
                FROM recurring_goal_saves rgs
                LEFT JOIN donation_goals g ON g.id = rgs.goal_id
                WHERE rgs.is_active = 1
                ORDER BY run_date ASC
                LIMIT ?
                ''',
                (limit,)
            )
            items = []
            for run_date, item_type, subtype, amount, icon, name in cursor.fetchall():
                items.append({
                    "run_date": run_date,
                    "item_type": item_type,
                    "subtype": subtype,
                    "amount": float(amount or 0),
                    "icon": icon or "",
                    "name": name or ""
                })
            return items
        finally:
            conn.close()
    
    @db_guard(lambda: ([], [], []))
    def get_transactions_by_category(self, period='month'):
        """Get transactions grouped by category for the current period"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            if period == 'month':
                cursor.execute('''
                    SELECT c.name, c.color, SUM(t.amount) as total
                    FROM transactions t
                    JOIN categories c ON t.category_id = c.id
                    WHERE t.type = 'expense' 
                    AND strftime('%Y-%m', t.date) = strftime('%Y-%m', 'now')
                    GROUP BY c.id
                    ORDER BY total DESC
                ''')
            else:            
                cursor.execute('''
                    SELECT c.name, c.color, SUM(t.amount) as total
                    FROM transactions t
                    JOIN categories c ON t.category_id = c.id
                    WHERE t.type = 'expense'
                    GROUP BY c.id
                    ORDER BY total DESC
                ''')
            
            results = cursor.fetchall()
            
            categories = []
            totals = []
            colors = []
            
            for name, color, total in results:
                categories.append(name)
                totals.append(total)
                colors.append(color)
            
            return categories, totals, colors
        finally:
            conn.close()
    
    def create_goal(self, name, target_amount, deadline_date, goal_type='dream', current_amount=0):
        """Create a new goal."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO donation_goals (name, target_amount, current_amount, deadline_date, goal_type)
                VALUES (?, ?, ?, ?, ?)
            ''', (name, target_amount, current_amount, deadline_date, goal_type))
            
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            self._log_db_error("create_goal", e)
            return False
        finally:
            conn.close()
    
    def create_donation_goal(self, name, target_amount, deadline_date):
        """Backward-compatible helper for donation-only goal creation."""
        return self.create_goal(name, target_amount, deadline_date, goal_type='donation', current_amount=0)

    @db_guard(list)
    def get_goals(self, goal_type=None, include_inactive=False):
        """Get goals, optionally filtered by type and active status."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            where_clauses = []
            params = []

            if not include_inactive:
                where_clauses.append("is_active = 1")
            if goal_type:
                where_clauses.append("goal_type = ?")
                params.append(goal_type)

            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
            cursor.execute(f'''
                SELECT id, name, target_amount, current_amount, deadline_date, is_active, goal_type
                FROM donation_goals
                {where_sql}
                ORDER BY deadline_date
            ''', params)
            
            goals = []
            for row in cursor.fetchall():
                goals.append({
                    'id': row[0],
                    'name': row[1],
                    'target_amount': row[2],
                    'current_amount': row[3],
                    'deadline_date': row[4],
                    'is_active': row[5],
                    'goal_type': row[6],
                    'progress': clamp_percentage((row[3] / row[2]) * 100 if row[2] > 0 else 0)
                })
            
            return goals
        finally:
            conn.close()

    def get_donation_goals(self):
        """Get active donation goals."""
        return self.get_goals('donation')

    def get_all_goals(self):
        """Get all goals including achieved/inactive ones."""
        return self.get_goals(include_inactive=True)
    
    def update_donation_goals(self, amount, conn=None):
        """Update donation goals with new donation"""
        close_conn = False
        if conn is None:
            conn = self.get_connection()
            close_conn = True
        
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE donation_goals 
                SET current_amount = current_amount + ? 
                WHERE is_active = 1 AND goal_type = 'donation'
            ''', (amount,))
            
            conn.commit()
        except sqlite3.Error as e:
            self._log_db_error("update_donation_goals", e)
            conn.rollback()
        finally:
            if close_conn:
                conn.close()
    
    def delete_goal(self, goal_id):
        """Delete a donation goal"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                DELETE FROM donation_goals WHERE id = ?
            ''', (goal_id,))
            
            conn.commit()
            return True
        except sqlite3.Error as e:
            self._log_db_error("delete_goal", e)
            return False
        finally:
            conn.close()

    def add_goal_progress(self, goal_id, amount):
        """Backward-compatible wrapper; use contribute_to_goal."""
        success, _ = self.contribute_to_goal(goal_id, amount)
        return success

    def contribute_to_goal(self, goal_id, amount):
        """Contribute money from balance to a specific goal."""
        if amount <= 0:
            return False, "Please enter an amount greater than zero."

        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT name, target_amount, current_amount, goal_type, is_active
                FROM donation_goals
                WHERE id = ?
            ''', (goal_id,))
            goal_row = cursor.fetchone()
            if not goal_row:
                return False, "Goal not found."

            goal_name, target_amount, current_amount, goal_type, is_active = goal_row
            if not is_active:
                return False, "This goal is already completed."

            current_balance = self.get_current_balance()
            if amount > current_balance:
                return False, "Insufficient funds to contribute this amount."

            transaction_type = 'donation' if goal_type == 'donation' else 'expense'
            description_prefix = "Donation goal contribution" if goal_type == 'donation' else "Dream goal savings"
            description = f"{description_prefix}: {goal_name}"

            cursor.execute('''
                INSERT INTO transactions (type, amount, category_id, description, date)
                VALUES (?, ?, NULL, ?, datetime('now'))
            ''', (transaction_type, amount, description))

            new_current = current_amount + amount
            is_complete = 1 if new_current >= target_amount else 0
            cursor.execute('''
                UPDATE donation_goals
                SET current_amount = ?, is_active = CASE WHEN ? = 1 THEN 0 ELSE is_active END
                WHERE id = ?
            ''', (new_current, is_complete, goal_id))
            conn.commit()
            if is_complete:
                return True, f"Goal achieved: {goal_name}"
            return True, f"Saved ${amount:,.2f} toward '{goal_name}'."
        except sqlite3.Error as e:
            conn.rollback()
            self._log_db_error("add_goal_progress", e)
            return False, "Database error while updating goal."
        finally:
            conn.close()

    def mark_goal_achieved(self, goal_id):
        """Mark a goal as achieved without adding additional money."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                UPDATE donation_goals
                SET is_active = 0
                WHERE id = ?
            ''', (goal_id,))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            self._log_db_error("mark_goal_achieved", e)
            return False
        finally:
            conn.close()
    
    def add_category(self, name, category_type, color, icon):
        """Add a custom category"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO categories (name, type, color, icon)
                VALUES (?, ?, ?, ?)
            ''', (name, category_type, color, icon))
            
            conn.commit()
            return True
        except sqlite3.Error as e:
            self._log_db_error("add_category", e)
            return False
        finally:
            conn.close()
    
    @db_guard(lambda: ([], [], [], []))
    def get_monthly_summary(self):
        """Get monthly income and expense summary"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT 
                    strftime('%Y-%m', date) as month,
                    SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) as income,
                    SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) as expense,
                    SUM(CASE WHEN type = 'donation' THEN amount ELSE 0 END) as donation
                FROM transactions
                GROUP BY strftime('%Y-%m', date)
                ORDER BY month DESC
                LIMIT ?
            ''', (AppConstants.MONTHLY_SUMMARY_LIMIT,))
            
            months = []
            incomes = []
            expenses = []
            donations = []
            
            for row in cursor.fetchall():
                months.append(row[0])
                incomes.append(row[1] or 0)
                expenses.append(row[2] or 0)
                donations.append(row[3] or 0)
            
                                              
            return months[::-1], incomes[::-1], expenses[::-1], donations[::-1]
        finally:
            conn.close()
    
                                                                 
    
    def set_budget(self, category_id, monthly_limit):
        """Set or update budget for a category"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO budgets (category_id, monthly_limit, is_active)
                VALUES (?, ?, 1)
            ''', (category_id, monthly_limit))
            
            conn.commit()
            return True
        except sqlite3.Error as e:
            self._log_db_error("set_budget", e)
            return False
        finally:
            conn.close()
    
    @db_guard(list)
    def get_budgets(self):
        """Get all budgets with category info"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT b.id, b.category_id, c.name, c.icon, c.color, 
                       b.monthly_limit, b.is_active,
                       COALESCE((
                           SELECT SUM(amount) 
                           FROM transactions t 
                           WHERE t.category_id = b.category_id 
                           AND t.type = 'expense'
                           AND strftime('%Y-%m', t.date) = strftime('%Y-%m', 'now')
                       ), 0) as current_spent
                FROM budgets b
                JOIN categories c ON b.category_id = c.id
                WHERE b.is_active = 1
                ORDER BY c.name
            ''')
            
            budgets = []
            for row in cursor.fetchall():
                current_spent = row[7]
                monthly_limit = row[5]
                percentage = (current_spent / monthly_limit) * 100 if monthly_limit > 0 else 0
                
                budgets.append({
                    'id': row[0],
                    'category_id': row[1],
                    'category_name': row[2],
                    'icon': row[3],
                    'color': row[4],
                    'monthly_limit': monthly_limit,
                    'is_active': row[6],
                    'current_spent': current_spent,
                    'percentage': percentage,
                    'percentage_clamped': clamp_percentage(percentage),
                    'remaining': monthly_limit - current_spent,
                    'exceeded': current_spent > monthly_limit
                })
            
            return budgets
        finally:
            conn.close()
    
    @db_guard(None)
    def get_category_budget(self, category_id):
        """Get budget for a specific category"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT monthly_limit FROM budgets 
                WHERE category_id = ? AND is_active = 1
            ''', (category_id,))
            
            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            conn.close()
    
    def delete_budget(self, budget_id):
        """Delete a budget"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                DELETE FROM budgets WHERE id = ?
            ''', (budget_id,))
            
            conn.commit()
            return True
        except sqlite3.Error as e:
            self._log_db_error("delete_budget", e)
            return False
        finally:
            conn.close()
    
    def check_budget_exceeded(self, category_id, new_amount):
        """Check if adding new amount will exceed budget"""
        budget_limit = self.get_category_budget(category_id)
        if not budget_limit:
            return {'exceeded': False, 'message': ''}
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
                                                            
            cursor.execute('''
                SELECT COALESCE(SUM(amount), 0) 
                FROM transactions 
                WHERE category_id = ? 
                AND type = 'expense'
                AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            ''', (category_id,))
            
            current_spent = cursor.fetchone()[0]
            new_total = current_spent + new_amount
            exceeded = new_total > budget_limit
            
            if exceeded:
                category = next((c for c in self.get_categories('expense') if c['id'] == category_id), {})
                category_name = category.get('name', 'Unknown')
                
                return {
                    'exceeded': True,
                    'category_name': category_name,
                    'budget_limit': budget_limit,
                    'current_spent': current_spent,
                    'new_total': new_total,
                    'excess': new_total - budget_limit,
                    'message': f"⚠️ Budget Exceeded!\n\nCategory: {category_name}\n"
                             f"Budget Limit: ${budget_limit:.2f}\n"
                             f"Already Spent: ${current_spent:.2f}\n"
                             f"This Purchase: ${new_amount:.2f}\n"
                             f"New Total: ${new_total:.2f}\n"
                             f"Excess: ${new_total - budget_limit:.2f}"
                }
            
            return {'exceeded': False, 'message': ''}
        except sqlite3.Error as e:
            self._log_db_error("check_budget_exceeded", e)
            return {'exceeded': False, 'message': ''}
        finally:
            conn.close()
    
    def add_budget_notification(self, category_id, budget_info):
        """Store budget notification (in real app, you might want to save to database)"""
                                      
        print("BUDGET NOTIFICATION:", budget_info['message'])
    
    def get_budget_summary(self):
        """Get budget summary for current month"""
        budgets = self.get_budgets()
        
        if not budgets:
            return {
                'total_budget': 0,
                'total_spent': 0,
                'remaining': 0,
                'exceeded_categories': 0,
                'total_categories': 0
            }
        
        total_budget = sum(b['monthly_limit'] for b in budgets)
        total_spent = sum(b['current_spent'] for b in budgets)
        exceeded_categories = sum(1 for b in budgets if b['exceeded'])
        
        return {
            'total_budget': total_budget,
            'total_spent': total_spent,
            'remaining': total_budget - total_spent,
            'exceeded_categories': exceeded_categories,
            'total_categories': len(budgets),
            'budget_usage_percentage': (total_spent / total_budget * 100) if total_budget > 0 else 0
        }

    @db_guard(0)
    def get_category_monthly_spent(self, category_id):
        """Get current month's spending for a specific expense category"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT COALESCE(SUM(amount), 0) 
                FROM transactions 
                WHERE category_id = ? 
                AND type = 'expense'
                AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            ''', (category_id,))
            return cursor.fetchone()[0]
        finally:
            conn.close()

                                                          
class OperationResult:
    def __init__(self, success, message, category_id=None, created_category=False, budget_info=None):
        self.success = success
        self.message = message
        self.category_id = category_id
        self.created_category = created_category
        self.budget_info = budget_info or {}

class FinanceService:
    def __init__(self, db):
        self.db = db
        self.category_budget_ratios = {
            'bills': 0.30,
            'food': 0.18,
            'transport': 0.10,
            'healthcare': 0.08,
            'education': 0.07,
            'shopping': 0.06,
            'entertainment': 0.05
        }

    @staticmethod
    def _extract_category_name(category_text):
        if not category_text:
            return ""
        return category_text.split(' ', 1)[1] if ' ' in category_text else category_text

    def resolve_category(self, category_id, category_text, category_type, color, icon):
        if category_id is None:
            return None, False, "Please select a valid category."
        
        if category_id != -1:
            return category_id, False, None
        
        category_name = self._extract_category_name(category_text)
        if not category_name:
            return None, False, "Please select a valid category."
        
        if not self.db.add_category(category_name, category_type, color, icon):
            return None, False, "Failed to add category."
        
        categories = self.db.get_categories(category_type)
        for cat in categories:
            if cat['name'] == category_name:
                return cat['id'], True, None
        
        return None, True, "Failed to find the new category."

    def add_income(self, amount, category_id, category_text, description):
        if amount <= 0:
            return OperationResult(False, "Please enter a positive amount.")
        
        resolved_id, created, error = self.resolve_category(
            category_id, category_text, 'income', Styles.SUCCESS_COLOR, '💰'
        )
        if error:
            return OperationResult(False, error, created_category=created)
        
        success, message = self.db.add_transaction('income', amount, resolved_id, description)
        return OperationResult(success, message, category_id=resolved_id, created_category=created)

    def prepare_expense(self, amount, category_id, category_text):
        if amount <= 0:
            return OperationResult(False, "Please enter a positive amount.")
        
        resolved_id, created, error = self.resolve_category(
            category_id, category_text, 'expense', Styles.DANGER_COLOR, '💳'
        )
        if error:
            return OperationResult(False, error, created_category=created)
        
        budget_info = self.db.check_budget_exceeded(resolved_id, amount)
        return OperationResult(True, "OK", category_id=resolved_id, created_category=created, budget_info=budget_info)

    def add_expense(self, amount, category_id, description):
        return self.db.add_transaction('expense', amount, category_id, description)

    def add_donation(self, amount, category_id, category_text, description):
        if amount <= 0:
            return OperationResult(False, "Please enter a positive amount.")
        
        resolved_id, created, error = self.resolve_category(
            category_id, category_text, 'donation', '#e67e22', ''
        )
        if error:
            return OperationResult(False, error, created_category=created)
        
        success, message = self.db.add_transaction('donation', amount, resolved_id, description)
        return OperationResult(success, message, category_id=resolved_id, created_category=created)

    def get_budget_status(self, category_id, amount, category_text):
        budget_limit = self.db.get_category_budget(category_id)
        if budget_limit is None:
            return None
        
        current_spent = self.db.get_category_monthly_spent(category_id)
        new_total = current_spent + amount
        remaining = budget_limit - current_spent
        category_name = self._extract_category_name(category_text)
        
        return {
            'category_name': category_name,
            'budget_limit': budget_limit,
            'current_spent': current_spent,
            'remaining': remaining,
            'new_total': new_total,
            'exceeded': new_total > budget_limit,
            'excess': max(0, new_total - budget_limit)
        }

    @staticmethod
    def savings_guidance(income, savings_rate=0.2):
        """Return recommended monthly savings based on income and a rate."""
        if income <= 0 or savings_rate <= 0:
            return 0
        return income * savings_rate

    @staticmethod
    def savings_projection(monthly_saving, annual_rate, periods, is_years=True):
        """Future value of a monthly saving with optional annual return."""
        if monthly_saving <= 0 or periods <= 0:
            return 0
        months = periods * 12 if is_years else periods
        if annual_rate <= 0:
            return monthly_saving * months
        monthly_rate = annual_rate / 12
        return monthly_saving * (((1 + monthly_rate) ** months - 1) / monthly_rate)

    @staticmethod
    def months_to_reach_target(target_amount, monthly_saving, annual_rate=0.0, max_months=1200):
        """Estimate number of months needed to reach a target amount."""
        if target_amount <= 0:
            return 0
        if monthly_saving <= 0:
            return None

        if annual_rate <= 0:
            months = int(target_amount / monthly_saving)
            if months * monthly_saving < target_amount:
                months += 1
            return months

        monthly_rate = annual_rate / 12
        balance = 0.0
        for month in range(1, max_months + 1):
            balance = balance * (1 + monthly_rate) + monthly_saving
            if balance >= target_amount:
                return month
        return None

    @staticmethod
    def required_monthly_saving(target_amount, periods, annual_rate=0.0, is_years=True):
        """Required monthly saving to reach a target in a fixed time."""
        if target_amount <= 0 or periods <= 0:
            return 0

        months = periods * 12 if is_years else periods
        if annual_rate <= 0:
            return target_amount / months

        monthly_rate = annual_rate / 12
        factor = ((1 + monthly_rate) ** months - 1) / monthly_rate
        if factor <= 0:
            return 0
        return target_amount / factor

    def category_budget_guidance(self, monthly_income, category_name):
        """Recommend a budget target for a category based on monthly income."""
        if monthly_income <= 0:
            return {
                'ok': False,
                'message': "Set monthly income first to get category budget guidance."
            }

        normalized = (category_name or "").strip().lower()
        ratio = self.category_budget_ratios.get(normalized, 0.08)
        recommended = monthly_income * ratio
        min_target = recommended * 0.8
        max_target = recommended * 1.2

        return {
            'ok': True,
            'category': category_name,
            'ratio': ratio,
            'recommended': recommended,
            'min_target': min_target,
            'max_target': max_target
        }

                                                                
class NotificationManager:
    """Manages notifications for goals and budgets"""
    
    def __init__(self, db, main_window):
        self.db = db
        self.main_window = main_window
        self._shown_events_by_day = {}
        self.notification_timer = QTimer()
        self.notification_timer.timeout.connect(self.check_notifications)
        self.notification_timer.start(AppConstants.NOTIFICATION_INTERVAL_MS)                      

    def _should_show_event(self, event_id):
        """Throttle recurring notifications to once per day per event."""
        today = date.today().isoformat()
        if self._shown_events_by_day.get(event_id) == today:
            return False
        self._shown_events_by_day[event_id] = today
        return True
        
    def check_notifications(self):
        """Check for notifications to show"""
        try:
            self.db.process_recurring_items()
            self.check_goal_deadlines()
            self.check_goal_completions()
        except Exception as e:
            print(f"Error checking notifications: {e}")
    
    def check_goal_deadlines(self):
        """Check if any goals have reached their deadline"""
        goals = self.db.get_goals()
        today = date.today()
        
        for goal in goals:
            try:
                deadline_date = datetime.strptime(goal['deadline_date'], "%Y-%m-%d").date()
                days_left = (deadline_date - today).days
                
                                                              
                if days_left == 0:
                    event_id = f"goal:{goal['id']}:deadline_today"
                    if self._should_show_event(event_id):
                        self.show_goal_notification(
                            f"🎯 Goal Deadline Today!\n"
                            f"'{goal['name']}' is due today!\n"
                            f"Progress: ${goal['current_amount']:,.2f} / ${goal['target_amount']:,.2f} ({goal['progress']:.1f}%)"
                        )
                elif days_left == 1:
                    event_id = f"goal:{goal['id']}:deadline_tomorrow"
                    if self._should_show_event(event_id):
                        self.show_goal_notification(
                            f"⏰ Goal Deadline Tomorrow!\n"
                            f"'{goal['name']}' is due tomorrow!\n"
                            f"Progress: ${goal['current_amount']:,.2f} / ${goal['target_amount']:,.2f} ({goal['progress']:.1f}%)"
                        )
                elif days_left == 7:
                    event_id = f"goal:{goal['id']}:deadline_7days"
                    if self._should_show_event(event_id):
                        self.show_goal_notification(
                            f"📅 Goal Deadline in 7 Days!\n"
                            f"'{goal['name']}' is due in 7 days!\n"
                            f"Progress: ${goal['current_amount']:,.2f} / ${goal['target_amount']:,.2f} ({goal['progress']:.1f}%)"
                        )
                elif days_left < 0:
                    event_id = f"goal:{goal['id']}:past_due"
                    if self._should_show_event(event_id):
                        self.show_goal_notification(
                            f"⚠️ Goal Past Due!\n"
                            f"'{goal['name']}' is {abs(days_left)} days past deadline!\n"
                            f"Progress: ${goal['current_amount']:,.2f} / ${goal['target_amount']:,.2f} ({goal['progress']:.1f}%)"
                        )
            except (TypeError, ValueError, KeyError):
                continue
    
    def check_goal_completions(self):
        """Check if any goals have been completed"""
        goals = self.db.get_goals()
        
        for goal in goals:
            if goal['current_amount'] >= goal['target_amount'] and goal['target_amount'] > 0:
                event_id = f"goal:{goal['id']}:achieved"
                if self._should_show_event(event_id):
                    self.show_goal_notification(
                        f"🎉 Goal Achieved!\n"
                        f"Congratulations! You've reached your goal: '{goal['name']}'\n"
                        f"Amount: ${goal['current_amount']:,.2f} / ${goal['target_amount']:,.2f} (100%)"
                    )
    
    def show_goal_notification(self, message):
        """Show a goal notification"""
        QTimer.singleShot(0, lambda: show_toast(self.main_window, message, level="warning", duration_ms=5000))
    
    def _show_notification(self, message):
        """Show notification in the main thread"""
        QTimer.singleShot(0, lambda: show_toast(self.main_window, message, level="warning", duration_ms=5000))


class ToastBanner(QFrame):
    """Small non-blocking toast shown at the bottom-right of the main window."""

    LEVEL_COLORS = {
        "success": "#2ecc71",
        "warning": "#f39c12",
        "danger": "#e74c3c",
        "info": "#3498db",
    }

    def __init__(self, message, level="info", parent=None):
        super().__init__(parent)
        self.level = level if level in self.LEVEL_COLORS else "info"
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(0)

        label = QLabel(message)
        label.setWordWrap(True)
        label.setStyleSheet("color: white; font-size: 13px;")
        layout.addWidget(label)

        self.setStyleSheet(
            f"QFrame {{ background-color: {self.LEVEL_COLORS[self.level]}; "
            "border-radius: 8px; border: 1px solid rgba(0,0,0,0.12); }}"
        )

    def show_for(self, duration_ms=2600):
        self.adjustSize()
        parent = self.parentWidget()
        if parent:
            geo = parent.frameGeometry()
            x = geo.x() + geo.width() - self.width() - 20
            y = geo.y() + geo.height() - self.height() - 20
            self.move(max(8, x), max(8, y))
        self.show()
        QTimer.singleShot(duration_ms, self.close)


def show_toast(anchor, message, level="info", duration_ms=2600):
    """Show a non-blocking toast anchored to the top-level window."""
    if not isinstance(anchor, QWidget):
        return
    window = anchor.window() or anchor
    active_toast = getattr(window, "_active_toast", None)
    if active_toast and active_toast.isVisible():
        active_toast.close()
    toast = ToastBanner(message, level=level, parent=window)
    setattr(window, "_active_toast", toast)
    toast.show_for(duration_ms=duration_ms)

                                                  
class Styles:
    """Centralized styles for the application"""
    
    PRIMARY_COLOR = "#3498db"
    SUCCESS_COLOR = "#2ecc71"
    WARNING_COLOR = "#f39c12"
    DANGER_COLOR = "#e74c3c"
    DARK_COLOR = "#2c3e50"
    LIGHT_COLOR = "#f8f9fa"
    GRAY_COLOR = "#95a5a6"
    BORDER_COLOR = "#dee2e6"
    CARD_BG = "#ffffff"
    
    @staticmethod
    def get_balance_card():
        return f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {Styles.PRIMARY_COLOR}, stop:1 #2980b9);
                border-radius: 16px;
                padding: 30px;
                color: white;
                border: none;
            }}
        """

                                                          
class LoadingScreen(QDialog):
    """Simple faux loading screen shown before the main window."""

    loading_finished = pyqtSignal()

    def __init__(self, parent=None, total_duration_ms=1500, tip_interval_ms=1200):
        super().__init__(parent)
        self.progress_value = 0
        self.elapsed_ms = 0
        self.total_duration_ms = max(1000, int(total_duration_ms))
        self.tip_interval_ms = max(1250, int(tip_interval_ms))
        self.progress_tick_ms = 35
        self.current_tip = ""
        self.tips = [
            "Tip: Keep food and bills budgets higher than entertainment.",
            "Tip: Review spending weekly to catch drift early.",
            "Tip: Save first, spend second. Treat savings like a bill.",
            "Tip: Small recurring expenses compound quickly.",
            "Tip: Use category budgets to stay realistic, not restrictive.",
            "Tip: Set donation goals to support causes you care about!",
            "Tip: Regularly review your categories and budgets to stay aligned with your goals.",
            "Tip: Use the monthly summary to track your progress and adjust as needed.",
            "Tip: Remember, the best budget is one that reflects your values and priorities, not just numbers on a page.",
            "Tip: Think first before making a purchase. Will it bring you joy or just clutter?",
            "Tip: Consider setting up an emergency fund to cover unexpected expenses and avoid financial stress.",
            "Tip: Don't forget to make somebody smile today!",
            "Tip: The best way to predict your financial future is to create it. Start budgeting today!",
            "Tip: Start donating from small amounts. Every bit helps and builds the habit of giving.",
            "Tip: Donating to those in need is better than spending it for yourself. It brings more happiness and fulfillment.",
            "Tip: Try to save 20% of your income each month. It can be a game changer for your financial health!",
            "Tip: Financial freedom is not a dream, it's a decision. Start budgeting and saving today to take control of your future.",
            "Tip: Don't let money control you. Take control of your money by budgeting, saving, and giving back.",
            "Tip: Don't be afraid to ask for help with your finances. There are many resources available to help you budget, save, and invest wisely.",
            "Tip: Don't be lazy with your finances. A little effort in budgeting and saving can go a long way towards achieving your financial goals.",
            "Tip: Ultimately, decide things yourself, as the best financial advice is the one that fits your unique situation and goals. Use tips as guidance, but trust your own judgment and values when making financial decisions.",
            "Tip: Money is not everything, don't be greedy.",
            "Tip: Don't be afraid to make big dreams, dream as high as you can, you can put your dreams on the Goals and Savings tab.",
            "Tip: Use the savings calculator to calculate how much you need to save!",
            "Tip: Set goals that you want to achieve in the Goals and Savings tab.",
            "Tip: There are several different modes in the savings calculator, so choose the ones that you need!",
            "Tip: Don't forget to money for your goals!",
            "Tip: Money doesn't grow on trees, but it does grow in accounts.",
            "Tip: The best way to save money is to not spend it in the first place. Avoid impulse purchases and unnecessary expenses to keep more money in your pocket.",
            "Tip: Saving a little is better than saving nothing. Even small contributions to your savings can add up over time and help you reach your financial goals.",
            "Tip: Don't let the fear of making a financial mistake hold you back. Everyone makes mistakes, but the important thing is to learn from them and keep moving forward towards your goals.",
            "Tip: Remember that your financial journey is unique to you. Don't compare yourself to others or feel pressured to keep up with their spending habits. Focus on your own goals and values, and make financial decisions that align with them.",
            "Tip: The best time to start budgeting and saving was yesterday. The second best time is now. Don't wait for the perfect moment, start taking control of your finances today!",
            "Tip: Don't be hardheaded, listen to the tips, they are here to help you! (But also, use your own judgment and values when making financial decisions.)",
            "Tip: Don't forget to have fun with your finances! Budgeting and saving doesn't have to be boring. Find ways to make it enjoyable, like setting fun goals, rewarding yourself for milestones, or sharing your progress with friends and family.",
            "Tip: Be careful when investing your money. Do your research and consider seeking advice from a financial professional before making any investment decisions.",
            "Tip: Don't forget to review your financial goals and progress regularly. Set aside time each month to check in on your budget, savings, and goals, and make adjustments as needed to stay on track.",
            "Tip: Fast ways of making money are usually not sustainable or may even be a scam. Focus on building long-term financial habits that will serve you well over time.",
            "Tip: Track all your expenses, even the small ones. They can add up silently and waste your money without you realizing it.",
            "Tip: Subcriptions are silent money wasters. Review your subscriptions regularly and cancel any that you don't use or need that much.",
            "Tip: Try searching for discounts, coupons, or cheaper alternatives before making a purchase. It can save you a lot of money in the long run.",
            "Tip: Not all free or cheap things are good, and not all expensive things are bad. Use your judgment to evaluate the value of a purchase, rather than just the price tag.",
            "Tip: Some cheaper or free alternatives can be just as good as their more expensive counterparts. Don't be afraid to try new things and find hidden gems that fit your budget.",
            "Tip: Don't waste you money just because of peer pressure or social media influence. Make financial decisions based on what you want yourself, not what others are doing.",
            "Tip: Remember that money is a tool, not a goal. Use it to support your values, goals, and happiness, rather than just accumulating it for its own sake.",
            "Tip: Don't gamble, it'll just waste your money and cause you stress. If you want to have fun, find free or low-cost activities that bring you joy without risking your financial health.",
            "Tip: Be generous with your money, but also with your time, kindness, and love. These are the things that truly enrich our lives and the lives of those around us.",
            "Tip: Don't be afraid to ask for help when facing financial difficulties. There are many resources available, including financial advisors, credit counseling services, and community organizations that can provide support and guidance.",
            "Tip: If you have the means, consider giving to those in need. Helping others can bring a sense of fulfillment and purpose that money alone cannot provide.",
            "Tip: Don't forget to give thanks for the money you have, and use it to bless others whenever you can. Generosity can bring more joy and fulfillment than material possessions alone.",
            "Tip: Money can be a powerful tool for good, but it can also be a source of stress and anxiety if not managed wisely. Take control of your finances by budgeting, saving, and giving back, and remember to seek help when needed.",
            "Tip: Don't let money be a source of conflict in your relationships. Communicate openly and honestly about your financial goals, values, and challenges with your loved ones, and work together to find solutions that support your shared vision for the future.",
            "Tip: Don't let financial setbacks discourage you. Everyone faces challenges at some point, but the important thing is to learn from them and keep moving forward towards your goals.",
            "Tip: Don't let money define your self-worth. Your value as a person is not determined by your bank account, but by your character, kindness, and the positive impact you have on others.",
            "Tip: Think about the things that you already have, and be grateful for them. Gratitude can help you appreciate what you have and reduce the desire for more, which can lead to better financial habits and a more contented life.",
            "Tip: Try to be creative with what you have. Instead of always buying new things, find ways to repurpose, reuse, or share resources with others. This can save you money and also reduce waste.",
            "Tip: Reuse things instead of throwing them away. Not only can this save you money, but it can also help reduce waste and benefit the environment.",
            "Tip: Pay your taxes, it's not just a legal obligation, but also a way to contribute to the common good and support the services and infrastructure that benefit us all.",
            "Tip: Don't spend money just to impress others. True wealth is not about showing off, but about living a fulfilling and meaningful life that aligns with your values and goals.",
            "Tip: Don't let the pursuit of money consume you. Remember to take time for the things that truly matter, like relationships, experiences, and personal growth.",
            "Tip: Family is way more important than money. Don't let financial stress or disagreements overshadow the love and connection you have with your family. Prioritize your relationships and work together to find solutions that support your shared goals and values.",
            "Tip: Don't forget to take care of your mental and physical health. Money can be a source of stress, but it's important to prioritize your well-being and seek help if you're struggling with financial anxiety or other related issues.",
            "Tip: Avoid suspicious get-rich-quick schemes or investments that promise high returns with little risk. If it sounds too good to be true, it probably is.",
            "Tip: Never enter your financial information on untrusted websites or share it with unknown individuals. Protect your personal and financial data to avoid scams and identity theft.",
            "Tip: Never gamble, not even a bit, it can lead to addiction and financial ruin. If you want to have fun, find free or low-cost activities that bring you joy without risking your financial health.",
            "Tip: Lotteries are specifically designed to take your money and give you nothing in return. Don't waste your hard-earned money on them, and instead focus on building sustainable financial habits that can lead to long-term success.",
            "Tip: Don't do anything illegal to make money. It can lead to serious consequences and harm others. Instead, focus on legal and ethical ways to earn and manage your money.",
            "Tip: Never do drugs, not only can it harm your health and well-being, but it can also lead to financial problems and legal issues. If you're struggling with substance abuse, seek help from a professional or support group.",
            "Tip: Illegal things are illegal for a reason, don't do it, it can lead to serious consequences and harm others. Instead, focus on legal and ethical ways to earn and manage your money.",
            "Tip: Piracy is not only illegal, but it also risks entering malware into your device.",
            "Tip: Instead of pirating, consider using free or open-source alternatives, or supporting creators by purchasing their work legally. This can help ensure that you get a safe and high-quality product while also supporting the people who create the content you enjoy.",
            "Tip: Education is one of the best investments you can make. Consider using your money to invest in your education and skills, which can lead to better job opportunities and financial stability in the long run.",
            "Tip: Don't be afraid to negotiate for better pay or prices. Whether it's asking for a raise at work or negotiating a bill, advocating for yourself can help you save money and increase your income over time.",
            "Tip: If you feel that you're being stuck on a 9 to 5 job, and is making you stressed, consider looking for other job opportunities that align better with your passions and values. Life is too short to be stuck in a job that doesn't bring you joy or fulfillment.",
            "Tip: Don't forget to take breaks and enjoy life outside of work. Money is important, but it's not everything. Make time for hobbies, relationships, and experiences that bring you happiness and fulfillment.",
            "Tip: You do need money for the future, but you also need to enjoy the present. Find a balance between saving for the future and enjoying life in the moment.",
            "Tip: Your life is yours to decide, don't listen to peer pressure or societal expectations when it comes to your finances. Make decisions that align with your values and goals, and don't be afraid to forge your own path.",
            "Tip: Be original with your financial goals and plans. Don't just copy what others are doing, but think about what you truly want and need, and create a financial plan that works for you.",
            "Tip: Sometimes, not listening is the best financial advice. Don't be afraid to ignore trends, fads, or pressure from others when it comes to your finances.",
            "Tip: Don't be lazy, try to walk to the restaurant instead of ordering delivery, it can save you money and also be good for your health.",
            "Tip: Save electricity by turning off lights and unplugging devices when not in use. It can save you money on your energy bill and also help the environment.",
            "Tip: Always follow the law, not just because it's the right thing to do, but also because it can help you avoid legal troubles and financial penalties that can arise from breaking the law.",
            "Tip: Follow the Terms of Service/Terms of Use of any service or product you use. Violating them can lead to account suspension, loss of access, or even legal action, which can have financial consequences.",
            "Tip: Read the fine print before signing any contracts or agreements. This can help you avoid hidden fees, unfavorable terms, or other issues that could lead to financial problems down the line.",
            "Tip: Be consistent with your financial habits. Regularly saving, budgeting, and reviewing your finances can help you build a strong financial foundation and achieve your goals over time.",
            "Tip: Don't be afraid to seek advice from trusted friends, family members, or financial professionals when you have questions or need guidance with your finances. Getting a second opinion can help you make more informed decisions and avoid costly mistakes.",
            "Tip: Don't do a dangerous stunt just for fame. Your safety and well-being are more important than any potential financial gain or social media attention.",
            "Tip: The best things in life are free.",
            "Tip: Don't forget that you are a rich man, because you have woken up with air in your lungs, and you have a chance to live another day. Be grateful for the blessings you have, and use your resources wisely to create a fulfilling and meaningful life.",
            "Tip: Save an emergency fund, it's better to be safe than sorry. An emergency fund can help you cover unexpected expenses without going into debt or derailing your financial goals.",
            "Tip: You can schedule income and expenses to help you manage it easily.",
            "Tip: Don't let a single person control you, not even your parents. You are the one who controls your life, and you should make your own decisions based on your values and goals.",
            "Tip: Keep in mind that nothing is 100% guaranteed, and there are always risks involved in financial decisions. Be prepared for unexpected outcomes and have a backup plan in case things don't go as expected.",
            "Tip: Remember to not trust anybody blindly, even financial advisors or experts. Do your own research and make informed decisions based on your own goals and values.",
            "Tip: Even this Finance Manager is not perfect, it may have bugs or issues, so use it as a tool to help you manage your finances, but also use your own judgment and common sense when making financial decisions.",
            "Tip: Don't forget to have fun with your finances! Budgeting and saving doesn't have to be boring. Find ways to make it enjoyable, like setting fun goals, rewarding yourself for milestones, or sharing your progress with friends and family.",
            "Tip: Don't be afraid to not give money to people who ask for it. It's okay to say no, and it's important to set boundaries to protect your financial well-being.",
            "Tip: God feeds all the birds, and He will feed you too. Don't stress about your money, trust that God will provide for your needs and guide you towards a fulfilling and generous life.",
            "Tip: If you get the whole wide world then what did you actually gain? Except some people that doesn't truly care about you. If you got some people that truly love and care you, you can't get much more from life than that.",
            "Tip: Do everything with all your heart, as working for the Lord, not for human masters. This can help you find purpose and fulfillment in your work, and also lead to financial blessings as you use your talents and resources to serve others.",
            "Tip: Give back to God what He has given you. Use your money to support your faith, your community, and those in need, and remember that true wealth is found in generosity and love, not just in material possessions.",
            "Tip: Don't forget to pray for wisdom and guidance in your financial decisions. With God's help, you can make wise choices that lead to financial stability and generosity.",
            "Tip: However good you save, without God's will, wealth won't last.",
            "Tip: Miracles from God happen, so don't be dismayed when facing a hard problem, it might just come!",
            "Tip: If you pray and work hard, God will bless your efforts and help you achieve your financial goals. Don't forget to ask for guidance and support in your financial journey.",
            "Tip: Don't forget to pray and ask God for wisdom and guidance in your financial decisions. With His help, you can make wise choices that lead to financial stability and generosity.",
            "Tip: Remember, you can survive without money, but you can't survive without God. Prioritize your relationship with Him above all else, and trust that He will provide for your needs and guide you towards a fulfilling and generous life.",
            "Tip: Just be yourself, be original, be authentic",
            "Tip: Do what you want, don't listen to what others say you should do. As at the end, you are the only one who knows your own struggles.",
            "Tip: What if everybody were original? It would be much better, because God actually creates us uniquely. Not everybody is meant to be the same, and that's a good thing.",
            "Tip: What if everybody were the same? It would be boring right? But it's actually what's happening right now, everyone is following another. So just be yourself.",
            "Tip: If you think why celebrities are famous, it's because they are original, they are themselves, and they are not afraid to be different.",
            "Tip: Find your specialty, everybody has them. Don't hide it, don't be embarrased about it, it might just be the thing that makes you successful.",
            "Tip: Try to be creative, find things that you can do that others can't, and do it. It can be a great way to make money and also find fulfillment in your work.",
            "Tip: If you don't find your purpose in life, you will just follow others and be disheartened when facing struggles. So find your purpose, it may be our specialty, or for your family, it can be anything; just find it.",
            "Tip: Find things that you enjoy, what makes you happy. Happines is way more important than just money.",
            "Tip: If you are forcing yourself to do something, it's most likely to be for money. Remember, it's just money, try to do things that makes you happy instead.",
            "Tip: Money is worthless, it's just a piece of paper (or coin, or a number in a screen). Yes you do need money, but it's not the one thing you need. Being happy is way way better.",
            "Tip: Don't be afraid to make a big decision, if it is better for you, then do it.",
            "Tip: People expect you (or even you expect yourself) to be a CEO (or smth), but it's not all sunshine and rainbows. They all have their own struggles, so do something that you truly want instead.",
            "Tip: Try to write your dreams, it can help you to suceed and be happy. Don't forget to write it origginally!",
            "Tip: Your own family has to be your No. 1 priority, not those that asks for help. They have other people to ask for help, but your family only has you.",
            "Tip: Prioritise your family, not only is it yor responsibility, but it can also avoid problems in the future.",
            "Tip: If you yourself don't have enough money for yourself ot your family, don't be afraid to not give to those in need. You are also in need currently.",
            "Tip: Don't let your ego control you, let people see who you really are, if you are poor, let them see you are poor, if you are rich, let them see you are rich. Don't be afraid to show your true self.",
            "Tip: Not all people that beg for money really need it, so donate to charities instead. (Remember that some charities are scams, so do your research before donating.)",
            "Tip: When investing, see how much money you actually get from it, not how much your current profit is. If you don't have the money on hand, that is not money, it's just a number.",
            "Tip: God's rule is not to restrict you, but to protect you. Don't be afraid of it, it is for your own good.",
            """Tip: Don't be afraid to ask for money if you truly need it (keyword here is "truly"), don't be stressed alone, but also don't be afraid to not give money if you truly don't have it. It's okay to ask for help.""",
            "Tip: Research wisely before doing payment with a new thing that you have found. It might be a fraud.",
            "Got a suggestion? Feel free to reach to me at gabrian.nicholas123@gmail.com",
            "Welcome to the Finance Manager!",
            "Welcome to the Finance Manager!",
            "Welcome to the Finance Manager!",
            "Welcome to the Finance Manager!",
            "Welcome to the Finance Manager!",
            "Welcome to the Finance Manager!", #6
            "Welcome to the Finance Manager!", #7 (67!!!) #Code easter egg
            "Welcome to the Finance Manager!" # 8 :(
        ]
        self.easter_egg_tips = [
            "Welcome to the Fimance Namager!",
            "Tip: Give me a (money) tip, NOW!!! (Just kidding, I'm the one giving you (not money) tips!)",
            "This message shows up in a 1 in a 30 chance! (But it may be even rarer if I add more tips and forgot to edit this)",
            "The above tip (which you can only know if you read the code) is now wrong, because I not only added more tips, but I changed the way Easter Eggs show up.",
            "Tip: DONATE TO ME, NOW!!! (Just kidding, don't donate to me, but seriously, consider donating to a cause you care about!)",
            "This is an Easter egg! You found it! Congrats! (Or maybe you just read the code...)",
            "Why are Easter eggs called so? Hmmm... well I don't know, but the Easter egg about the Easter egg chance is now wro. Wait, I shouldn't say that! Oops, sorry!",
            "I Love WarpVar",
            "INTGR",
            "Seriously, check out INTGR through our Discord server! https://discord.gg/nDPYaZnbmc",
            "Welcome back to Kiwi News.",
            'John 14:6 - Jesus answered, “I am the way and the truth and the life. No one comes to the Father except through me.',
            "Colossians 3:23 - Whatever you do, work at it with all your heart, as working for the Lord, not for human masters.",
            'I asked Jesus, "How much do you love me?". Jesus replied, "This much", and stretched his arms on the cross and died for me.',
            "John 3:16 - For God so loved the world that he gave his one and only Son, that whoever believes in him shall not perish but have eternal life.",
            "The greatest price of all has already been paid. Jesus paid it all.",
            "You finding this Finance Manager might just be a blessing from God. Don't forget to give thanks and use it to bless others!",
            'John 8:12 - When Jesus spoke again to the people, he said, "I am the light of the world. Whoever follows me will never walk in darkness, but will have the light of life."'
            "Made by CtrlAltSpace" #Do not remove this line
        ]
        self.setup_ui()
        self.setup_timers()

    def setup_ui(self):
        self.setWindowTitle("Loading")
        self.setModal(True)
        self.setFixedSize(560, 300)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
        )
        icon = resolve_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title = QLabel("Finance Manager")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #2c3e50;")
        layout.addWidget(title)

        subtitle = QLabel("Preparing your dashboard...\n\nThis program is licensed under the GNU AGPL v3. No warranty provided.")
        subtitle.setStyleSheet("font-size: 14px; color: #6c757d;")
        layout.addWidget(subtitle)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setMinimumHeight(28)
        self.progress_bar.setStyleSheet(Styles.get_progress_bar())
        layout.addWidget(self.progress_bar)

        self.current_tip = self.pick_random_tip()
        self.tip_label = QLabel(self.current_tip)
        self.tip_label.setWordWrap(True)
        self.tip_label.setStyleSheet(
            "font-size: 13px; color: #2c3e50; background-color: #f8f9fa; "
            "border: 1px solid #dee2e6; border-radius: 8px; padding: 10px;"
        )
        layout.addWidget(self.tip_label)
        layout.addStretch()

    def setup_timers(self):
        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self.advance_progress)
        self.progress_timer.start(self.progress_tick_ms)
        self.tip_timer = None

    def showEvent(self, event):
        super().showEvent(event)
        self.center_on_screen()

    def center_on_screen(self):
        screen = self.screen() or QApplication.primaryScreen()
        if not screen:
            return
        screen_geo = screen.availableGeometry()
        x = screen_geo.x() + (screen_geo.width() - self.width()) // 2
        y = screen_geo.y() + (screen_geo.height() - self.height()) // 2
        self.move(x, y)

    def advance_progress(self):
        self.elapsed_ms += self.progress_tick_ms
        self.progress_value = min(100, int((self.elapsed_ms / self.total_duration_ms) * 100))
        self.progress_bar.setValue(self.progress_value)

        if self.progress_value >= 100:
            self.progress_timer.stop()
            if self.tip_timer is not None:
                self.tip_timer.stop()
            self.loading_finished.emit()
            self.accept()

    def rotate_tip(self):
        self.current_tip = self.pick_random_tip(self.current_tip)
        self.tip_label.setText(self.current_tip)

    def pick_random_tip(self, previous_tip=""):
        """Pick a random tip, with a low chance to show an easter-egg tip."""
        show_easter_egg = random.random() < AppConstants.LOADING_EASTER_EGG_CHANCE
        pool = self.easter_egg_tips if show_easter_egg and self.easter_egg_tips else self.tips
        if not pool:
            return ""
        if len(pool) == 1:
            return pool[0]

        choice = random.choice(pool)
        while choice == previous_tip:
            choice = random.choice(pool)
        return choice

    @staticmethod
    def get_card_style():
        return f"""
            QFrame {{
                background-color: {Styles.CARD_BG};
                border-radius: 12px;
                padding: 24px;
                border: 1px solid {Styles.BORDER_COLOR};
            }}
        """
    
    @staticmethod
    def get_section_title():
        return """
            QLabel {
                font-size: 20px;
                font-weight: bold;
                color: #2c3e50;
                padding: 5px 0;
            }
        """
    
    @staticmethod
    def get_subtitle():
        return """
            QLabel {
                font-size: 16px;
                font-weight: 600;
                color: #34495e;
                padding: 3px 0;
            }
        """
    
    @staticmethod
    def get_primary_button():
        return f"""
            QPushButton {{
                background-color: {Styles.PRIMARY_COLOR};
                color: white;
                border: none;
                padding: 14px 28px;
                border-radius: 8px;
                font-weight: 600;
                font-size: 15px;
                min-height: 48px;
            }}
            QPushButton:hover {{
                background-color: #2980b9;
            }}
            QPushButton:pressed {{
                background-color: #21618c;
            }}
            QPushButton:disabled {{
                background-color: {Styles.GRAY_COLOR};
                color: #bdc3c7;
            }}
        """
    
    @staticmethod
    def get_success_button():
        return f"""
            QPushButton {{
                background-color: {Styles.SUCCESS_COLOR};
                color: white;
                border: none;
                padding: 14px 28px;
                border-radius: 8px;
                font-weight: 600;
                font-size: 15px;
                min-height: 48px;
            }}
            QPushButton:hover {{
                background-color: #27ae60;
            }}
            QPushButton:pressed {{
                background-color: #219653;
            }}
        """
    
    @staticmethod
    def get_danger_button():
        return f"""
            QPushButton {{
                background-color: {Styles.DANGER_COLOR};
                color: white;
                border: none;
                padding: 14px 28px;
                border-radius: 8px;
                font-weight: 600;
                font-size: 15px;
                min-height: 48px;
            }}
            QPushButton:hover {{
                background-color: #c0392b;
            }}
            QPushButton:pressed {{
                background-color: #a93226;
            }}
        """
    
    @staticmethod
    def get_warning_button():
        return f"""
            QPushButton {{
                background-color: {Styles.WARNING_COLOR};
                color: white;
                border: none;
                padding: 14px 28px;
                border-radius: 8px;
                font-weight: 600;
                font-size: 15px;
                min-height: 48px;
            }}
            QPushButton:hover {{
                background-color: #d68910;
            }}
            QPushButton:pressed {{
                background-color: #b9770e;
            }}
        """
    
    @staticmethod
    def get_secondary_button():
        return f"""
            QPushButton {{
                background-color: white;
                color: {Styles.DARK_COLOR};
                border: 1px solid {Styles.BORDER_COLOR};
                padding: 12px 24px;
                border-radius: 8px;
                font-weight: 500;
                font-size: 14px;
                min-height: 44px;
            }}
            QPushButton:hover {{
                background-color: {Styles.LIGHT_COLOR};
                border-color: {Styles.PRIMARY_COLOR};
            }}
            QPushButton:pressed {{
                background-color: #e9ecef;
            }}
        """
    
    @staticmethod
    def get_input_style():
        return f"""
            QLineEdit, QDoubleSpinBox, QDateEdit, QTextEdit, QSpinBox {{
                padding: 12px;
                border: 1px solid {Styles.BORDER_COLOR};
                border-radius: 8px;
                background-color: white;
                font-size: 14px;
                min-height: 44px;
                color: {Styles.DARK_COLOR};
            }}
            QDoubleSpinBox, QSpinBox {{
                padding-right: 12px;
            }}
            QDoubleSpinBox::up-button, QSpinBox::up-button {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 0px;
                border: none;
                background: transparent;
            }}
            QDoubleSpinBox::down-button, QSpinBox::down-button {{
                subcontrol-origin: padding;
                subcontrol-position: bottom right;
                width: 0px;
                border: none;
                background: transparent;
            }}
            QComboBox {{
                padding: 12px;
                padding-right: 12px;
                border: 1px solid {Styles.BORDER_COLOR};
                border-radius: 8px;
                background-color: white;
                font-size: 14px;
                min-height: 56px;
                color: {Styles.DARK_COLOR};
            }}
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{
                border: 2px solid {Styles.PRIMARY_COLOR};
                padding: 11px;
            }}
            QComboBox::drop-down {{
                width: 0px;
                border: none;
                background: transparent;
            }}
            QComboBox::down-arrow {{
                image: none;
                width: 0px;
                height: 0px;
            }}
            QComboBox QAbstractItemView {{
                border: 1px solid {Styles.BORDER_COLOR};
                border-radius: 8px;
                background-color: white;
                font-size: 14px;
                selection-background-color: {Styles.PRIMARY_COLOR};
                selection-color: white;
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 40px;
                padding: 10px 12px;
                color: {Styles.DARK_COLOR};
                background-color: white;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {Styles.LIGHT_COLOR};
                color: {Styles.DARK_COLOR};
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: {Styles.PRIMARY_COLOR};
                color: white;
            }}
        """
    
    @staticmethod
    def get_progress_bar():
        return f"""
            QProgressBar {{
                border: 1px solid {Styles.BORDER_COLOR};
                border-radius: 6px;
                text-align: center;
                height: 24px;
                font-size: 12px;
                font-weight: 500;
            }}
            QProgressBar::chunk {{
                background-color: {Styles.PRIMARY_COLOR};
                border-radius: 5px;
            }}
        """
    
    @staticmethod
    def get_list_widget():
        return f"""
            QListWidget {{
                border: 1px solid {Styles.BORDER_COLOR};
                border-radius: 8px;
                background-color: white;
                outline: none;
                color: {Styles.DARK_COLOR};
            }}
            QListWidget::item {{
                border-bottom: 1px solid {Styles.BORDER_COLOR};
                padding: 16px;
                color: {Styles.DARK_COLOR};
            }}
            QListWidget::item:selected {{
                background-color: {Styles.PRIMARY_COLOR};
                color: white;
                border-radius: 4px;
            }}
            QListWidget::item:hover {{
                background-color: {Styles.LIGHT_COLOR};
                color: {Styles.DARK_COLOR};
            }}
            QListWidget::item:selected {{
                background-color: {Styles.PRIMARY_COLOR};
                color: white;
            }}
            QListWidget::item:selected:hover {{
                background-color: {Styles.PRIMARY_COLOR};
                color: white;
            }}
        """
    
    @staticmethod
    def get_table_style():
        return f"""
            QTableWidget {{
                border: 1px solid {Styles.BORDER_COLOR};
                border-radius: 8px;
                background-color: white;
                gridline-color: #e9ecef;
                outline: none;
            }}
            QTableWidget::item {{
                padding: 0px 10px;
                border: none;
            }}
            QHeaderView::section {{
                background-color: #f8f9fa;
                padding: 12px;
                border: none;
                border-bottom: 2px solid {Styles.BORDER_COLOR};
                font-weight: 600;
                color: {Styles.DARK_COLOR};
                height: 40px;
            }}
            QHeaderView {{
                background: #f8f9fa;
            }}
            QTableWidget::item:selected {{
                background-color: {Styles.PRIMARY_COLOR};
                color: white;
            }}
        """
    
    @staticmethod
    def get_app_style():
        return f"""
            QMainWindow {{
                background-color: {Styles.LIGHT_COLOR};
            }}
            QWidget {{
                font-family: 'Segoe UI', 'Arial', sans-serif;
            }}
            QLabel {{
                color: {Styles.DARK_COLOR};
            }}
            QCheckBox {{
                color: {Styles.DARK_COLOR};
                font-size: 14px;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 1px solid {Styles.BORDER_COLOR};
                border-radius: 4px;
                background: white;
            }}
            QCheckBox::indicator:checked {{
                background: {Styles.PRIMARY_COLOR};
                border-color: {Styles.PRIMARY_COLOR};
            }}
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
            QScrollArea > QWidget > QWidget {{
                background-color: transparent;
            }}
            QScrollBar:vertical {{
                border: none;
                background: #f1f1f1;
                width: 10px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: #c1c1c1;
                border-radius: 5px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: #a8a8a8;
            }}
        """

                                                                                       
for _style_name in [
    "get_card_style",
    "get_section_title",
    "get_subtitle",
    "get_primary_button",
    "get_success_button",
    "get_danger_button",
    "get_warning_button",
    "get_secondary_button",
    "get_input_style",
    "get_progress_bar",
    "get_list_widget",
    "get_table_style",
    "get_app_style",
]:
    if not hasattr(Styles, _style_name) and hasattr(LoadingScreen, _style_name):
        setattr(Styles, _style_name, staticmethod(getattr(LoadingScreen, _style_name)))

                                                   
class BudgetDialog(QDialog):
    """Dialog for setting budget"""
    
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setup_ui()
        
    def setup_ui(self):
        self.setWindowTitle("Set Budget")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        
                            
        category_layout = QVBoxLayout()
        category_layout.setSpacing(8)
        category_layout.addWidget(QLabel("Category:"))
        
        self.category_combo = QComboBox()
        self.category_combo.setStyleSheet(Styles.get_input_style())
        
                                      
        categories = self.db.get_categories('expense')
        for cat in categories:
            self.category_combo.addItem(f"{cat['icon']} {cat['name']}", cat['id'])
        
        category_layout.addWidget(self.category_combo)
        layout.addLayout(category_layout)
        
                       
        amount_layout = QVBoxLayout()
        amount_layout.setSpacing(8)
        amount_layout.addWidget(QLabel("Monthly Budget Limit:"))
        
        self.amount_input = QDoubleSpinBox()
        self.amount_input.setPrefix("$ ")
        self.amount_input.setRange(AppConstants.MIN_AMOUNT, AppConstants.MAX_BUDGET_AMOUNT)
        self.amount_input.setValue(AppConstants.DEFAULT_BUDGET_AMOUNT)
        self.amount_input.setStyleSheet(Styles.get_input_style())
        amount_layout.addWidget(self.amount_input)
        layout.addLayout(amount_layout)

                   
        self.hint_label = QLabel("Tip: Set monthly income before creating budgets.")
        self.hint_label.setStyleSheet("color: #6c757d; font-size: 12px; padding: 6px 8px;")
        layout.addWidget(self.hint_label)
        self.update_income_hint()
        
                                        
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #6c757d; font-size: 12px; padding: 8px; background-color: #f8f9fa; border-radius: 6px;")
        self.info_label.hide()
        layout.addWidget(self.info_label)
        
                                           
        self.category_combo.currentIndexChanged.connect(self.update_info)
        self.update_info()
        
                 
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.validate_and_accept)
        button_box.rejected.connect(self.reject)
        
                       
        for button in button_box.buttons():
            if button.text() == "OK":
                button.setStyleSheet(Styles.get_primary_button())
            else:
                button.setStyleSheet(Styles.get_secondary_button())
        
        layout.addWidget(button_box)
        
    def validate_and_accept(self):
        """Validate budget rules before accepting"""
        self.update_income_hint()
        category_id = self.category_combo.currentData()
        amount = self.amount_input.value()

        if category_id is None:
            QMessageBox.warning(self, "Error", "Please select a category.")
            return

        if amount <= 0:
            QMessageBox.warning(self, "Error", "Please enter a positive amount.")
            return

        monthly_income = self.db.get_monthly_income()
        if monthly_income <= 0:
            QMessageBox.warning(
                self,
                "Set Monthly Income",
                "Please set your monthly income before creating budgets."
            )
            return

                                                 
        existing_budget = self.db.get_category_budget(category_id)
        current_total = sum(b['monthly_limit'] for b in self.db.get_budgets())
        if existing_budget is not None:
            current_total -= existing_budget
        new_total = current_total + amount
        if new_total > monthly_income:
            QMessageBox.warning(
                self,
                "Budget Limit Exceeded",
                f"Total budgets cannot exceed monthly income.\n\n"
                f"Monthly Income: ${monthly_income:,.2f}\n"
                f"Current Total Budgets: ${current_total:,.2f}\n"
                f"Proposed Total Budgets: ${new_total:,.2f}"
            )
            return

        self.accept()

    def update_info(self):
        """Update information about current spending"""
        category_id = self.category_combo.currentData()
        if not category_id:
            return
        
                                                        
        current_spent = self.db.get_category_monthly_spent(category_id)
        
        if current_spent > 0:
            self.info_label.setText(
                f"⚠️ Already spent ${current_spent:.2f} this month in this category."
            )
            self.info_label.show()
        else:
            self.info_label.hide()

    def update_income_hint(self):
        """Show/hide income hint based on current monthly income"""
        if self.db.get_monthly_income() > 0:
            self.hint_label.hide()
        else:
            self.hint_label.show()
    
    def get_budget_data(self):
        """Get the budget data from dialog"""
        return {
            'category_id': self.category_combo.currentData(),
            'monthly_limit': self.amount_input.value()
        }

class IncomeSettingDialog(QDialog):
    """Dialog for setting monthly income"""
    
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setup_ui()
        
    def setup_ui(self):
        self.setWindowTitle("Set Monthly Income")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        
                                
        current_income = self.db.get_monthly_income()
        current_label = QLabel(f"Current Monthly Income: ${current_income:,.2f}")
        current_label.setStyleSheet("font-weight: 600; color: #2c3e50; padding: 12px; background-color: #f8f9fa; border-radius: 8px;")
        layout.addWidget(current_label)
        
                          
        income_layout = QVBoxLayout()
        income_layout.setSpacing(8)
        income_layout.addWidget(QLabel("New Monthly Income:"))
        
        self.income_input = QDoubleSpinBox()
        self.income_input.setPrefix("$ ")
        self.income_input.setRange(0, AppConstants.MAX_AMOUNT)
        self.income_input.setValue(current_income if current_income > 0 else AppConstants.DEFAULT_MONTHLY_INCOME)
        self.income_input.setStyleSheet(Styles.get_input_style())
        income_layout.addWidget(self.income_input)
        layout.addLayout(income_layout)
        
             
        tip_label = QLabel("💡 This will be used for budget calculations and alerts.")
        tip_label.setStyleSheet("color: #6c757d; font-size: 12px; padding: 8px; background-color: #fff8e1; border-radius: 6px;")
        layout.addWidget(tip_label)
        
                 
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
                       
        for button in button_box.buttons():
            if button.text() == "OK":
                button.setStyleSheet(Styles.get_primary_button())
            else:
                button.setStyleSheet(Styles.get_secondary_button())
        
        layout.addWidget(button_box)
    
    def get_income(self):
        """Get the income value"""
        return self.income_input.value()

                                                   
class BalanceCard(QFrame):
    """Custom widget for displaying balance"""
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        
    def setup_ui(self):
        self.setStyleSheet(Styles.get_balance_card())
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        self.title_label = QLabel("Current Balance")
        self.title_label.setStyleSheet("font-size: 18px; color: rgba(255,255,255,0.9); font-weight: 500;")
        
        self.balance_label = QLabel("$0.00")
        self.balance_label.setFont(QFont("Segoe UI", 42, QFont.Weight.Bold))
        self.balance_label.setStyleSheet("color: white;")
        
        layout.addWidget(self.title_label)
        layout.addWidget(self.balance_label, alignment=Qt.AlignmentFlag.AlignCenter)
        
                                        
        layout.addSpacing(10)
        
    def update_balance(self, amount):
        """Update the balance display"""
        self.balance_label.setText(f"${amount:,.2f}")

class StatCard(QFrame):
    """Widget for displaying statistics"""
    
    def __init__(self, title, value, color, icon=""):
        super().__init__()
        self.title = title
        self.value = value
        self.color = color
        self.icon = icon
        self.setup_ui()
        
    def setup_ui(self):
        self.setStyleSheet(Styles.get_card_style())
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
                        
        title_layout = QHBoxLayout()
        
        if self.icon:
            icon_label = QLabel(self.icon)
            icon_label.setStyleSheet("font-size: 24px;")
            title_layout.addWidget(icon_label)
        
        title_label = QLabel(self.title)
        title_label.setStyleSheet("color: #6c757d; font-size: 14px; font-weight: 500;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        
        self.value_label = QLabel(self.value)
        self.value_label.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        self.value_label.setStyleSheet(f"color: {self.color};")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addLayout(title_layout)
        layout.addWidget(self.value_label)
        
    def update_value(self, value):
        """Update the value display"""
        self.value_label.setText(value)

class TransactionWidget(QWidget):
    """Widget for displaying a single transaction"""
    
    def __init__(self, transaction_type, amount, category, description, date):
        super().__init__()
        self.transaction_type = transaction_type
        self.amount = amount
        self.category = category
        self.description = description
        self.date = date
        self.setup_ui()
        
    def setup_ui(self):
        self.setMinimumHeight(70)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)
        
                                   
        icon_frame = QFrame()
        icon_frame.setFixedSize(48, 48)
        icon_frame.setStyleSheet(f"""
            background-color: {self.color_for_type(True)};
            border-radius: 8px;
        """)
        
        icon_layout = QVBoxLayout(icon_frame)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        
        if self.transaction_type == 'income':
            icon = "💰"
        elif self.transaction_type == 'expense':
            icon = "💳"
        else:            
            icon = "❤️"
            
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 24px;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_layout.addWidget(icon_label)
        
        layout.addWidget(icon_frame)
        
                 
        details_layout = QVBoxLayout()
        details_layout.setSpacing(4)
        
        category_text = f"{self.category}"
        if self.description:
            category_text += f" - {self.description}"
            
        category_label = QLabel(category_text)
        category_label.setStyleSheet(f"font-weight: 600; color: {self.color_for_type()}; font-size: 15px;")
        category_label.setWordWrap(True)
        
        date_label = QLabel(self.date)
        date_label.setStyleSheet("color: #6c757d; font-size: 13px;")
        
        details_layout.addWidget(category_label)
        details_layout.addWidget(date_label)
        layout.addLayout(details_layout)
        
        layout.addStretch()
        
                
        amount_prefix = "+" if self.transaction_type == 'income' else "-"
        amount_label = QLabel(f"{amount_prefix}${self.amount:,.2f}")
        amount_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        amount_label.setStyleSheet(f"color: {self.color_for_type()};")
        layout.addWidget(amount_label)
        
    def color_for_type(self, background=False):
        if self.transaction_type == 'income':
            return "#27ae60" if background else Styles.SUCCESS_COLOR
        elif self.transaction_type == 'expense':
            return "#c0392b" if background else Styles.DANGER_COLOR
        else:
            return "#d68910" if background else Styles.WARNING_COLOR

                                                 
class DashboardView(QWidget):
    """Main dashboard view"""
    
    refresh_requested = pyqtSignal()
    add_income_requested = pyqtSignal()
    add_expense_requested = pyqtSignal()
    save_goal_requested = pyqtSignal()
    
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setup_ui()
        self.refresh_data()
        
    def setup_ui(self):
                                                           
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("border: none; background: transparent;")
        
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(24)
        main_layout.setContentsMargins(32, 24, 32, 32)                      
        
                
        header_layout = QHBoxLayout()
        
        title = QLabel("Dashboard Overview")
        title.setStyleSheet(Styles.get_section_title())
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        refresh_button = QPushButton("🔄 Refresh")
        refresh_button.setStyleSheet(Styles.get_secondary_button())
        refresh_button.clicked.connect(self.refresh_data)
        header_layout.addWidget(refresh_button)
        
        main_layout.addLayout(header_layout)
        
                              
        self.balance_card = BalanceCard()
        main_layout.addWidget(self.balance_card)

                               
        actions_frame = QFrame()
        actions_frame.setStyleSheet(Styles.get_card_style())
        actions_layout = QHBoxLayout(actions_frame)
        actions_layout.setSpacing(12)

        add_income_btn = QPushButton("+ Add Income")
        add_income_btn.setStyleSheet(Styles.get_success_button())
        add_income_btn.clicked.connect(self.add_income_requested.emit)

        add_expense_btn = QPushButton("- Add Expense")
        add_expense_btn.setStyleSheet(Styles.get_primary_button())
        add_expense_btn.clicked.connect(self.add_expense_requested.emit)

        save_goal_btn = QPushButton("🎯 Save to Goal")
        save_goal_btn.setStyleSheet(Styles.get_warning_button())
        save_goal_btn.clicked.connect(self.save_goal_requested.emit)

        actions_layout.addWidget(add_income_btn)
        actions_layout.addWidget(add_expense_btn)
        actions_layout.addWidget(save_goal_btn)
        main_layout.addWidget(actions_frame)
        
                              
        budget_frame = QFrame()
        budget_frame.setStyleSheet(Styles.get_card_style())
        budget_layout = QVBoxLayout(budget_frame)
        budget_layout.setSpacing(16)
        
        budget_title_layout = QHBoxLayout()
        budget_title = QLabel("🎯 Budget Overview")
        budget_title.setStyleSheet(Styles.get_subtitle())
        budget_title_layout.addWidget(budget_title)
        budget_title_layout.addStretch()
        
        set_income_button = QPushButton("💰 Set Income")
        set_income_button.setStyleSheet(Styles.get_secondary_button())
        set_income_button.clicked.connect(self.show_income_dialog)
        budget_title_layout.addWidget(set_income_button)
        
        budget_layout.addLayout(budget_title_layout)
        
                      
        self.budget_stats_layout = QVBoxLayout()
        budget_layout.addLayout(self.budget_stats_layout)
        
        main_layout.addWidget(budget_frame)

                                  
        upcoming_frame = QFrame()
        upcoming_frame.setStyleSheet(Styles.get_card_style())
        upcoming_layout = QVBoxLayout(upcoming_frame)
        upcoming_layout.setSpacing(12)

        upcoming_title = QLabel("Upcoming")
        upcoming_title.setStyleSheet(Styles.get_subtitle())
        upcoming_layout.addWidget(upcoming_title)

        self.upcoming_items_layout = QVBoxLayout()
        self.upcoming_items_layout.setSpacing(8)
        upcoming_layout.addLayout(self.upcoming_items_layout)
        main_layout.addWidget(upcoming_frame)
        
                          
        stats_title = QLabel("Financial Summary")
        stats_title.setStyleSheet(Styles.get_subtitle())
        main_layout.addWidget(stats_title)
        
        stats_grid = self.create_stats_grid()
        main_layout.addWidget(stats_grid)
        
                             
        recent_frame = QFrame()
        recent_frame.setStyleSheet(Styles.get_card_style())
        recent_layout = QVBoxLayout(recent_frame)
        recent_layout.setSpacing(16)
        
        recent_title_layout = QHBoxLayout()
        recent_title = QLabel("Recent Transactions")
        recent_title.setStyleSheet(Styles.get_subtitle())
        recent_title_layout.addWidget(recent_title)
        recent_title_layout.addStretch()
        
        view_all_button = QPushButton("View All")
        view_all_button.setStyleSheet(Styles.get_secondary_button())
        view_all_button.setMinimumWidth(100)
        view_all_button.clicked.connect(self.view_all_transactions)
        recent_title_layout.addWidget(view_all_button)
        
        recent_layout.addLayout(recent_title_layout)
        
                                             
        self.recent_transactions_widget = QWidget()
        self.recent_layout = QVBoxLayout(self.recent_transactions_widget)
        self.recent_layout.setSpacing(8)
        self.recent_layout.setContentsMargins(0, 0, 0, 0)
        
        transactions_scroll = QScrollArea()
        transactions_scroll.setWidget(self.recent_transactions_widget)
        transactions_scroll.setWidgetResizable(True)
        transactions_scroll.setMinimumHeight(350)               
        transactions_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                width: 12px;
                background: #f5f5f5;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #c1c1c1;
                border-radius: 6px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #a8a8a8;
            }
        """)
        
        recent_layout.addWidget(transactions_scroll)
        main_layout.addWidget(recent_frame, 1)                            
        
        scroll_area.setWidget(container)
        
                                                
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_area)
        
    def create_stats_grid(self):
        frame = QFrame()
        frame.setStyleSheet(Styles.get_card_style())
        grid = QGridLayout(frame)
        grid.setSpacing(20)
        grid.setContentsMargins(0, 0, 0, 0)
        
        self.income_card = StatCard("Total Income", "$0", Styles.SUCCESS_COLOR, "💰")
        self.expense_card = StatCard("Total Expenses", "$0", Styles.DANGER_COLOR, "💳")
        self.donation_card = StatCard("Total Donated", "$0", Styles.WARNING_COLOR, "❤️")
        
                               
        net_value = "$0"
        net_color = Styles.SUCCESS_COLOR
        self.net_card = StatCard("Net Savings", net_value, net_color, "📈")
        
        grid.addWidget(self.income_card, 0, 0)
        grid.addWidget(self.expense_card, 0, 1)
        grid.addWidget(self.donation_card, 1, 0)
        grid.addWidget(self.net_card, 1, 1)
        
        return frame
        
    def refresh_data(self):
        """Refresh all data on the dashboard"""
                        
        balance = self.db.get_current_balance()
        self.balance_card.update_balance(balance)
        
                                
        self.update_budget_overview()
        
                      
        stats = self.db.get_summary_stats()
        self.income_card.update_value(f"${stats['total_income']:,.2f}")
        self.expense_card.update_value(f"${stats['total_expenses']:,.2f}")
        self.donation_card.update_value(f"${stats['total_donations']:,.2f}")
        
                                          
        net_savings = stats['total_income'] - stats['total_expenses'] - stats['total_donations']
        net_color = Styles.SUCCESS_COLOR if net_savings >= 0 else Styles.DANGER_COLOR
        self.net_card.value_label.setStyleSheet(f"color: {net_color};")
        self.net_card.update_value(f"${net_savings:,.2f}")
        
                                    
        self.update_recent_transactions(stats['recent_transactions'])
        self.update_upcoming_items()

    def update_upcoming_items(self):
        """Refresh upcoming recurring transaction/goal-save list."""
        for i in reversed(range(self.upcoming_items_layout.count())):
            widget = self.upcoming_items_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        items = self.db.get_upcoming_recurring_items(limit=6)
        if not items:
            label = QLabel("No upcoming recurring items.")
            label.setStyleSheet("color: #6c757d; font-size: 13px; padding: 8px;")
            self.upcoming_items_layout.addWidget(label)
            return

        today = date.today()
        for item in items:
            try:
                run_date = datetime.strptime(item['run_date'], "%Y-%m-%d").date()
                days = (run_date - today).days
            except Exception:
                days = None

            if days is None:
                due_text = f"on {item['run_date']}"
            elif days < 0:
                due_text = f"{abs(days)} day(s) overdue"
            elif days == 0:
                due_text = "today"
            else:
                due_text = f"in {days} day(s)"

            kind = "Goal save" if item["item_type"] == "goal_save" else item["subtype"].capitalize()
            icon = item["icon"] or "•"
            row = QLabel(
                f"{icon} {item['name']} - ${item['amount']:,.2f} ({kind}, {due_text})"
            )
            row.setStyleSheet("color: #2c3e50; font-size: 13px; padding: 6px; background-color: #f8f9fa; border-radius: 6px;")
            row.setWordWrap(True)
            self.upcoming_items_layout.addWidget(row)
        
    def update_budget_overview(self):
        """Update the budget overview section"""
                                
        for i in reversed(range(self.budget_stats_layout.count())):
            widget = self.budget_stats_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        
        budget_summary = self.db.get_budget_summary()
        monthly_income = self.db.get_monthly_income()
        
        if monthly_income == 0:
                               
            setup_label = QLabel("📊 Set your monthly income to enable budget tracking")
            setup_label.setStyleSheet("color: #6c757d; font-size: 14px; padding: 20px; text-align: center;")
            setup_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.budget_stats_layout.addWidget(setup_label)
            return
        
        if budget_summary['total_categories'] == 0:
                            
            no_budget_label = QLabel("🎯 No budgets set yet. Visit the Budgets tab to create budgets.")
            no_budget_label.setStyleSheet("color: #6c757d; font-size: 14px; padding: 20px; text-align: center;")
            no_budget_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.budget_stats_layout.addWidget(no_budget_label)
            return
        
                             
        summary_text = f"""
        <div style='color: #2c3e50;'>
            <div style='margin-bottom: 8px;'>
                <span style='font-weight: 600;'>Monthly Income:</span> 
                <span style='color: {Styles.SUCCESS_COLOR}; font-weight: 600;'>${monthly_income:,.2f}</span>
            </div>
            <div style='margin-bottom: 8px;'>
                <span style='font-weight: 600;'>Total Budget:</span> 
                <span style='color: #3498db; font-weight: 600;'>${budget_summary['total_budget']:,.2f}</span>
            </div>
            <div style='margin-bottom: 8px;'>
                <span style='font-weight: 600;'>Spent This Month:</span> 
                <span style='color: {Styles.DANGER_COLOR if budget_summary['total_spent'] > budget_summary['total_budget'] else Styles.WARNING_COLOR}; font-weight: 600;'>
                    ${budget_summary['total_spent']:,.2f}
                </span>
            </div>
            <div style='margin-bottom: 8px;'>
                <span style='font-weight: 600;'>Remaining:</span> 
                <span style='color: {Styles.SUCCESS_COLOR if budget_summary['remaining'] >= 0 else Styles.DANGER_COLOR}; font-weight: 600;'>
                    ${abs(budget_summary['remaining']):,.2f}
                </span>
            </div>
        </div>
        """
        
        summary_label = QLabel()
        summary_label.setTextFormat(Qt.TextFormat.RichText)
        summary_label.setText(summary_text)
        summary_label.setStyleSheet("font-size: 14px; padding: 16px; background-color: #f8f9fa; border-radius: 8px;")
        self.budget_stats_layout.addWidget(summary_label)
        
                                               
        usage_percentage = budget_summary['budget_usage_percentage']
        clamped_usage = clamp_percentage(usage_percentage)
        progress_bar = QProgressBar()
        progress_bar.setRange(0, int(AppConstants.PROGRESS_MAX))
        progress_bar.setValue(int(clamped_usage))
        
                                  
        if usage_percentage >= AppConstants.BUDGET_OVER_THRESHOLD:
            progress_bar.setStyleSheet(f"""
                QProgressBar {{
                    border: 1px solid {Styles.BORDER_COLOR};
                    border-radius: 6px;
                    text-align: center;
                    height: 24px;
                    font-size: 12px;
                    font-weight: 500;
                }}
                QProgressBar::chunk {{
                    background-color: {Styles.DANGER_COLOR};
                    border-radius: 5px;
                }}
            """)
            progress_bar.setFormat(f"OVER BUDGET: {usage_percentage:.1f}%")
        elif usage_percentage >= AppConstants.BUDGET_WARNING_THRESHOLD:
            progress_bar.setStyleSheet(f"""
                QProgressBar {{
                    border: 1px solid {Styles.BORDER_COLOR};
                    border-radius: 6px;
                    text-align: center;
                    height: 24px;
                    font-size: 12px;
                    font-weight: 500;
                }}
                QProgressBar::chunk {{
                    background-color: {Styles.WARNING_COLOR};
                    border-radius: 5px;
                }}
            """)
            progress_bar.setFormat(f"{usage_percentage:.1f}% Used")
        else:
            progress_bar.setStyleSheet(f"""
                QProgressBar {{
                    border: 1px solid {Styles.BORDER_COLOR};
                    border-radius: 6px;
                    text-align: center;
                    height: 24px;
                    font-size: 12px;
                    font-weight: 500;
                }}
                QProgressBar::chunk {{
                    background-color: {Styles.SUCCESS_COLOR};
                    border-radius: 5px;
                }}
            """)
            progress_bar.setFormat(f"{usage_percentage:.1f}% Used")
        
        self.budget_stats_layout.addWidget(progress_bar)
        
                                          
        if budget_summary['exceeded_categories'] > 0:
            warning_label = QLabel(f"⚠️ {budget_summary['exceeded_categories']} category(ies) over budget!")
            warning_label.setStyleSheet(f"color: {Styles.DANGER_COLOR}; font-weight: 600; padding: 12px; background-color: #ffeaea; border-radius: 8px;")
            self.budget_stats_layout.addWidget(warning_label)
    
    def show_income_dialog(self):
        """Show dialog to set monthly income"""
        dialog = IncomeSettingDialog(self.db, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_income = dialog.get_income()
            if self.db.set_monthly_income(new_income):
                self.refresh_data()
                show_toast(self, f"Monthly income set to ${new_income:,.2f}", level="success")
            else:
                QMessageBox.critical(self, "Error", "Failed to update monthly income.")
        
    def update_recent_transactions(self, transactions):
        """Update the recent transactions list"""
                                     
        for i in reversed(range(self.recent_layout.count())):
            widget = self.recent_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        
                              
        if not transactions:
            empty_label = QLabel("No transactions yet. Add your first transaction!")
            empty_label.setStyleSheet("color: #95a5a6; font-style: italic; font-size: 14px; padding: 40px;")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.recent_layout.addWidget(empty_label)
        else:
            for trans in transactions:
                trans_type, amount, category, icon, description, trans_date = trans
                if not category:
                    category = "Uncategorized"
                if icon:
                    category = f"{icon} {category}"
                    
                             
                try:
                    date_obj = datetime.strptime(trans_date, "%Y-%m-%d %H:%M:%S")
                    formatted_date = date_obj.strftime("%b %d, %I:%M %p")
                except (TypeError, ValueError):
                    formatted_date = trans_date
                    
                widget = TransactionWidget(trans_type, amount, category, description, formatted_date)
                self.recent_layout.addWidget(widget)
        
        self.recent_layout.addStretch()
    
    def view_all_transactions(self):
        """Show all transactions in a dialog."""
        transactions = self.db.get_all_transactions()
        if not transactions:
            show_toast(self, "No transactions found.", level="info")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("All Transactions")
        dialog.resize(980, 620)
        dialog_layout = QVBoxLayout(dialog)
        dialog_layout.setContentsMargins(16, 16, 16, 16)
        dialog_layout.setSpacing(12)

        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Date", "Type", "Category", "Description", "Amount"])
        table.setRowCount(len(transactions))
        table.setStyleSheet(Styles.get_table_style())
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        for row_idx, trans in enumerate(transactions):
            trans_type, amount, category, icon, description, trans_date = trans

            try:
                date_obj = datetime.strptime(trans_date, "%Y-%m-%d %H:%M:%S")
                formatted_date = date_obj.strftime("%Y-%m-%d %I:%M %p")
            except Exception:
                formatted_date = trans_date

            category_text = category if category else "Uncategorized"
            if icon:
                category_text = f"{icon} {category_text}"

            type_label = trans_type.capitalize()
            amount_prefix = "+" if trans_type == "income" else "-"
            amount_color = Styles.SUCCESS_COLOR if trans_type == "income" else Styles.DANGER_COLOR
            amount_item = QTableWidgetItem(f"{amount_prefix}${amount:,.2f}")
            amount_item.setForeground(QColor(amount_color))
            amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            table.setItem(row_idx, 0, QTableWidgetItem(formatted_date))
            table.setItem(row_idx, 1, QTableWidgetItem(type_label))
            table.setItem(row_idx, 2, QTableWidgetItem(category_text))
            table.setItem(row_idx, 3, QTableWidgetItem(description or ""))
            table.setItem(row_idx, 4, amount_item)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        dialog_layout.addWidget(table)
        dialog.exec()

class IncomeView(QWidget):
    """View for adding income"""
    
    transaction_added = pyqtSignal()
    
    def __init__(self, db, service=None):
        super().__init__()
        self.db = db
        self.service = service or FinanceService(db)
        self.setup_ui()
        
    def setup_ui(self):
                                                
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("border: none; background: transparent;")
        
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(28)
        main_layout.setContentsMargins(32, 24, 32, 40)                      
        
                
        header_layout = QHBoxLayout()
        
        title = QLabel("Add Income")
        title.setStyleSheet(Styles.get_section_title())
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        refresh_button = QPushButton("🔄 Refresh")
        refresh_button.setStyleSheet(Styles.get_secondary_button())
        refresh_button.clicked.connect(self.refresh_view)
        header_layout.addWidget(refresh_button)
        main_layout.addLayout(header_layout)
        
                         
        balance_frame = QFrame()
        balance_frame.setStyleSheet(Styles.get_card_style())
        balance_layout = QVBoxLayout(balance_frame)
        balance_layout.setSpacing(8)
        
        balance_title = QLabel("Current Balance")
        balance_title.setStyleSheet(Styles.get_subtitle())
        
        self.balance_label = QLabel("$0.00")
        self.balance_label.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        self.balance_label.setStyleSheet(f"color: {Styles.SUCCESS_COLOR};")
        
        balance_layout.addWidget(balance_title)
        balance_layout.addWidget(self.balance_label)
        
        main_layout.addWidget(balance_frame)
        
              
        form_frame = QFrame()
        form_frame.setStyleSheet(Styles.get_card_style())
        form_layout = QFormLayout(form_frame)
        form_layout.setVerticalSpacing(20)
        form_layout.setHorizontalSpacing(24)
        form_layout.setContentsMargins(24, 24, 24, 24)
        
                
        self.amount_input = QDoubleSpinBox()
        self.amount_input.setRange(AppConstants.MIN_AMOUNT, AppConstants.MAX_AMOUNT)
        self.amount_input.setPrefix("$ ")
        self.amount_input.setDecimals(2)
        self.amount_input.setValue(AppConstants.MIN_AMOUNT)
        self.amount_input.setStyleSheet(Styles.get_input_style())
        
                  
        self.category_combo = QComboBox()
        self.category_combo.setStyleSheet(Styles.get_input_style())
        self.load_categories()
        
                     
        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("e.g., Salary from work, Birthday gift, etc.")
        self.description_input.setStyleSheet(Styles.get_input_style())

        self.repeat_check = QComboBox()
        self.repeat_check.addItem("No", False)
        self.repeat_check.addItem("Yes", True)
        self.repeat_check.setStyleSheet(Styles.get_input_style())
        self.repeat_every = QSpinBox()
        self.repeat_every.setRange(1, 365)
        self.repeat_every.setValue(1)
        self.repeat_every.setStyleSheet(Styles.get_input_style())
        self.repeat_unit = QComboBox()
        self.repeat_unit.addItems(["Days", "Weeks", "Months"])
        self.repeat_unit.setStyleSheet(Styles.get_input_style())
        self.repeat_start = QDateEdit()
        self.repeat_start.setDate(QDate.currentDate())
        self.repeat_start.setCalendarPopup(True)
        self.repeat_start.setStyleSheet(Styles.get_input_style())
        self.repeat_every_label = QLabel("Repeat every:")
        self.repeat_start_label = QLabel("Start date:")
        repeat_row = QHBoxLayout()
        repeat_row.setSpacing(10)
        repeat_row.addWidget(self.repeat_every)
        repeat_row.addWidget(self.repeat_unit)

        form_layout.addRow(QLabel("Amount:"), self.amount_input)
        form_layout.addRow(QLabel("Category:"), self.category_combo)
        form_layout.addRow(QLabel("Description:"), self.description_input)
        form_layout.addRow(QLabel("Auto repeat:"), self.repeat_check)
        form_layout.addRow(self.repeat_every_label, repeat_row)
        form_layout.addRow(self.repeat_start_label, self.repeat_start)
        self.repeat_check.currentIndexChanged.connect(self._update_repeat_controls)
        self._update_repeat_controls()
        
        main_layout.addWidget(form_frame)
        
                    
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.add_button = QPushButton("➕ Add Income")
        self.add_button.clicked.connect(self.add_income)
        self.add_button.setStyleSheet(Styles.get_success_button())
        self.add_button.setMinimumWidth(200)
        button_layout.addWidget(self.add_button)
        button_layout.addStretch()
        
        main_layout.addLayout(button_layout)
        
                                           
        main_layout.addStretch()
        
        scroll_area.setWidget(container)
        
                    
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_area)
        
                        
        self.update_balance()

    def refresh_view(self):
        """Refresh visible data in this tab."""
        self.load_categories()
        self.update_balance()
    
    def load_categories(self):
        """Load income categories into the combo box"""
        self.category_combo.clear()
        categories = self.db.get_categories('income')
        
        if not categories:
                                                         
            for name, color, icon in DEFAULT_INCOME_CATEGORIES:
                self.category_combo.addItem(f"{icon} {name}", -1)
        else:
            for cat in categories:
                self.category_combo.addItem(f"{cat['icon']} {cat['name']}", cat['id'])
        
    def update_balance(self):
        """Update the balance display"""
        balance = self.db.get_current_balance()
        self.balance_label.setText(f"${balance:,.2f}")
    def add_income(self):
        """Add income transaction"""
        amount = self.amount_input.value()
        category_id = self.category_combo.currentData()
        category_text = self.category_combo.currentText()
        description = self.description_input.text().strip()

        result = self.service.add_income(amount, category_id, category_text, description)

        if result.created_category:
            self.load_categories()

        if result.success:
            if self.repeat_check.currentData():
                scheduled = self.db.add_recurring_transaction(
                    "income",
                    amount,
                    result.category_id,
                    description,
                    self.repeat_start.date().toString("yyyy-MM-dd"),
                    self.repeat_every.value(),
                    self._repeat_unit_to_db(self.repeat_unit.currentText())
                )
                if not scheduled:
                    QMessageBox.warning(self, "Warning", "Income added, but failed to create recurring schedule.")
            show_toast(self, "Income added successfully!", level="success")
            self.clear_form()
            self.update_balance()
            self.transaction_added.emit()
        else:
            if "positive amount" in result.message.lower():
                QMessageBox.warning(self, "Invalid Amount", result.message)
            else:
                QMessageBox.critical(self, "Error", result.message)

    def clear_form(self):
        """Clear the form inputs"""
        self.amount_input.setValue(AppConstants.MIN_AMOUNT)
        self.description_input.clear()
        self.repeat_check.setCurrentIndex(0)

    def _repeat_unit_to_db(self, text):
        mapping = {"Days": "day", "Weeks": "week", "Months": "month"}
        return mapping.get(text, "month")

    def _update_repeat_controls(self, *_):
        enabled = bool(self.repeat_check.currentData())
        self.repeat_every_label.setVisible(enabled)
        self.repeat_every.setVisible(enabled)
        self.repeat_every.setEnabled(enabled)
        self.repeat_unit.setVisible(enabled)
        self.repeat_unit.setEnabled(enabled)
        self.repeat_start_label.setVisible(enabled)
        self.repeat_start.setVisible(enabled)
        self.repeat_start.setEnabled(enabled)

class ExpenseView(QWidget):
    """View for adding expenses"""
    
    transaction_added = pyqtSignal()
    
    def __init__(self, db, service=None):
        super().__init__()
        self.db = db
        self.service = service or FinanceService(db)
        self.setup_ui()
        
    def setup_ui(self):
                                                
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("border: none; background: transparent;")
        
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(28)
        main_layout.setContentsMargins(32, 24, 32, 40)                      
        
                
        header_layout = QHBoxLayout()
        
        title = QLabel("Add Expense")
        title.setStyleSheet(Styles.get_section_title())
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        refresh_button = QPushButton("🔄 Refresh")
        refresh_button.setStyleSheet(Styles.get_secondary_button())
        refresh_button.clicked.connect(self.refresh_view)
        header_layout.addWidget(refresh_button)
        main_layout.addLayout(header_layout)
        
                      
        balance_frame = QFrame()
        balance_frame.setStyleSheet(Styles.get_card_style())
        balance_layout = QVBoxLayout(balance_frame)
        balance_layout.setSpacing(12)
        
        balance_title = QLabel("Current Balance")
        balance_title.setStyleSheet(Styles.get_subtitle())
        
        self.balance_label = QLabel("$0.00")
        self.balance_label.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        self.balance_label.setStyleSheet(f"color: {Styles.PRIMARY_COLOR};")
        
        self.balance_warning = QLabel("")
        self.balance_warning.setStyleSheet(f"color: {Styles.DANGER_COLOR}; font-weight: 600; padding: 8px; border-radius: 6px; background-color: #ffeaea;")
        self.balance_warning.hide()
        
        balance_layout.addWidget(balance_title)
        balance_layout.addWidget(self.balance_label)
        balance_layout.addWidget(self.balance_warning)
        
        main_layout.addWidget(balance_frame)
        
                                                           
        self.budget_warning = QLabel("")
        self.budget_warning.setStyleSheet(f"""
            color: {Styles.WARNING_COLOR};
            font-weight: 600;
            padding: 12px;
            border-radius: 8px;
            background-color: #fff8e1;
            border: 1px solid #ffd54f;
        """)
        self.budget_warning.hide()
        self.budget_warning.setWordWrap(True)
        main_layout.addWidget(self.budget_warning)
        
              
        form_frame = QFrame()
        form_frame.setStyleSheet(Styles.get_card_style())
        form_layout = QFormLayout(form_frame)
        form_layout.setVerticalSpacing(20)
        form_layout.setHorizontalSpacing(24)
        form_layout.setContentsMargins(24, 24, 24, 24)
        
                
        self.amount_input = QDoubleSpinBox()
        self.amount_input.setRange(AppConstants.MIN_AMOUNT, AppConstants.MAX_AMOUNT)
        self.amount_input.setPrefix("$ ")
        self.amount_input.setDecimals(2)
        self.amount_input.setValue(AppConstants.MIN_AMOUNT)
        self.amount_input.valueChanged.connect(self.check_balance_and_budget)
        self.amount_input.setStyleSheet(Styles.get_input_style())
        
                  
        self.category_combo = QComboBox()
        self.category_combo.setStyleSheet(Styles.get_input_style())
        self.category_combo.currentIndexChanged.connect(self.check_budget)
        self.load_categories()
        
                     
        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("e.g., Groceries, Movie tickets, etc.")
        self.description_input.setStyleSheet(Styles.get_input_style())

        self.repeat_check = QComboBox()
        self.repeat_check.addItem("No", False)
        self.repeat_check.addItem("Yes", True)
        self.repeat_check.setStyleSheet(Styles.get_input_style())
        self.repeat_every = QSpinBox()
        self.repeat_every.setRange(1, 365)
        self.repeat_every.setValue(1)
        self.repeat_every.setStyleSheet(Styles.get_input_style())
        self.repeat_unit = QComboBox()
        self.repeat_unit.addItems(["Days", "Weeks", "Months"])
        self.repeat_unit.setStyleSheet(Styles.get_input_style())
        self.repeat_start = QDateEdit()
        self.repeat_start.setDate(QDate.currentDate())
        self.repeat_start.setCalendarPopup(True)
        self.repeat_start.setStyleSheet(Styles.get_input_style())
        self.repeat_every_label = QLabel("Repeat every:")
        self.repeat_start_label = QLabel("Start date:")
        repeat_row = QHBoxLayout()
        repeat_row.setSpacing(10)
        repeat_row.addWidget(self.repeat_every)
        repeat_row.addWidget(self.repeat_unit)

        form_layout.addRow(QLabel("Amount:"), self.amount_input)
        form_layout.addRow(QLabel("Category:"), self.category_combo)
        form_layout.addRow(QLabel("Description:"), self.description_input)
        form_layout.addRow(QLabel("Auto repeat:"), self.repeat_check)
        form_layout.addRow(self.repeat_every_label, repeat_row)
        form_layout.addRow(self.repeat_start_label, self.repeat_start)
        self.repeat_check.currentIndexChanged.connect(self._update_repeat_controls)
        self._update_repeat_controls()
        
        main_layout.addWidget(form_frame)
        
                              
        self.budget_info_label = QLabel("")
        self.budget_info_label.setStyleSheet("color: #6c757d; font-size: 13px; padding: 8px; background-color: #f8f9fa; border-radius: 6px;")
        self.budget_info_label.hide()
        main_layout.addWidget(self.budget_info_label)
        
                    
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.add_button = QPushButton("➖ Add Expense")
        self.add_button.clicked.connect(self.add_expense)
        self.add_button.setStyleSheet(Styles.get_primary_button())
        self.add_button.setMinimumWidth(200)
        button_layout.addWidget(self.add_button)
        button_layout.addStretch()
        
        main_layout.addLayout(button_layout)
        
                                           
        main_layout.addStretch()
        
        scroll_area.setWidget(container)
        
                    
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_area)
        
                        
        self.update_balance()
        self.check_balance()
        self.check_budget()

    def refresh_view(self):
        """Refresh visible data in this tab."""
        self.load_categories()
        self.update_balance()
        self.check_balance()
        self.check_budget()
    
    def load_categories(self):
        """Load expense categories into the combo box"""
        self.category_combo.clear()
        categories = self.db.get_categories('expense')
        
        if not categories:
                                                          
            for name, color, icon in DEFAULT_EXPENSE_CATEGORIES:
                self.category_combo.addItem(f"{icon} {name}", -1)
        else:
            for cat in categories:
                self.category_combo.addItem(f"{cat['icon']} {cat['name']}", cat['id'])
    
    def update_balance(self):
        """Update the balance display"""
        current_balance = self.db.get_current_balance()
        self.balance_label.setText(f"${current_balance:,.2f}")
    
    def check_balance(self):
        """Check if expense amount exceeds balance"""
        if not hasattr(self, "add_button"):
            return
        amount = self.amount_input.value()
        current_balance = self.db.get_current_balance()
        
        if amount > current_balance:
            self.balance_warning.setText(
                f"⚠️ Insufficient funds\n"
                f"Expense: ${amount:,.2f} | Balance: ${current_balance:,.2f}"
            )
            self.balance_warning.show()
            self.add_button.setEnabled(False)
            self.add_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Styles.GRAY_COLOR};
                    color: white;
                    border: none;
                    padding: 14px 28px;
                    border-radius: 8px;
                    font-weight: 600;
                    font-size: 15px;
                    min-height: 48px;
                }}
            """)
        else:
            self.balance_warning.hide()
            self.add_button.setEnabled(True)
            self.add_button.setStyleSheet(Styles.get_primary_button())
    
    def check_balance_and_budget(self):
        """Check both balance and budget when amount changes"""
        self.check_balance()
        self.check_budget()
    
    def check_budget(self):
        """Check if expense would exceed budget"""
                                                             
        if not hasattr(self, 'budget_info_label'):
            return

        category_id = self.category_combo.currentData()
        amount = self.amount_input.value()

        if category_id is None or category_id == -1:
            self.budget_info_label.hide()
            self.budget_warning.hide()
            return

        status = self.service.get_budget_status(category_id, amount, self.category_combo.currentText())
        if not status:
            self.budget_info_label.hide()
            self.budget_warning.hide()
            return

        self.budget_info_label.setText(
            f"📊 {status['category_name']} Budget: ${status['budget_limit']:.2f}\n"
            f"   Spent: ${status['current_spent']:.2f} | Remaining: ${status['remaining']:.2f}"
        )
        self.budget_info_label.show()

        if status['exceeded']:
            self.budget_warning.setText(
                f"⚠️ BUDGET ALERT!\n"
                f"This purchase (${amount:.2f}) would exceed your {status['category_name']} budget by ${status['excess']:.2f}!\n"
                f"Budget: ${status['budget_limit']:.2f} | New Total: ${status['new_total']:.2f}"
            )
            self.budget_warning.show()
        else:
            self.budget_warning.hide()
    def add_expense(self):
        """Add expense transaction with budget check"""
        amount = self.amount_input.value()
        category_id = self.category_combo.currentData()
        category_text = self.category_combo.currentText()
        description = self.description_input.text().strip()

        prep = self.service.prepare_expense(amount, category_id, category_text)
        if prep.created_category:
            self.load_categories()

        if not prep.success:
            if "positive amount" in prep.message.lower():
                QMessageBox.warning(self, "Invalid Amount", prep.message)
            else:
                QMessageBox.warning(self, "Category Error", prep.message)
            return

        budget_info = prep.budget_info

        success, message = self.service.add_expense(amount, prep.category_id, description)

        if success:
            if self.repeat_check.currentData():
                scheduled = self.db.add_recurring_transaction(
                    "expense",
                    amount,
                    prep.category_id,
                    description,
                    self.repeat_start.date().toString("yyyy-MM-dd"),
                    self.repeat_every.value(),
                    self._repeat_unit_to_db(self.repeat_unit.currentText())
                )
                if not scheduled:
                    QMessageBox.warning(self, "Warning", "Expense added, but failed to create recurring schedule.")
            if budget_info.get('exceeded'):
                show_toast(
                    self,
                    f"Budget exceeded by ${budget_info['excess']:.2f}. Expense was still recorded.",
                    level="warning",
                    duration_ms=3500
                )
            else:
                show_toast(self, "Expense recorded successfully! 💳", level="success")

            self.clear_form()
            self.update_balance()
            self.transaction_added.emit()
        else:
            QMessageBox.critical(self, "Error", message)

    def clear_form(self):
        """Clear the form inputs"""
        self.amount_input.setValue(AppConstants.MIN_AMOUNT)
        self.description_input.clear()
        self.repeat_check.setCurrentIndex(0)
        self.check_balance()
        self.check_budget()

    def _repeat_unit_to_db(self, text):
        mapping = {"Days": "day", "Weeks": "week", "Months": "month"}
        return mapping.get(text, "month")

    def _update_repeat_controls(self, *_):
        enabled = bool(self.repeat_check.currentData())
        self.repeat_every_label.setVisible(enabled)
        self.repeat_every.setVisible(enabled)
        self.repeat_every.setEnabled(enabled)
        self.repeat_unit.setVisible(enabled)
        self.repeat_unit.setEnabled(enabled)
        self.repeat_start_label.setVisible(enabled)
        self.repeat_start.setVisible(enabled)
        self.repeat_start.setEnabled(enabled)
        self.check_balance()
        self.check_budget()

class DonationView(QWidget):
    """View for adding donations"""
    
    transaction_added = pyqtSignal()
    
    def __init__(self, db, service=None):
        super().__init__()
        self.db = db
        self.service = service or FinanceService(db)
        self.setup_ui()
        
    def setup_ui(self):
                                                
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("border: none; background: transparent;")
        
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(28)
        main_layout.setContentsMargins(32, 24, 32, 40)                      
        
                
        header_layout = QHBoxLayout()
        
        title = QLabel("Make a Donation")
        title.setStyleSheet(Styles.get_section_title())
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        refresh_button = QPushButton("🔄 Refresh")
        refresh_button.setStyleSheet(Styles.get_secondary_button())
        refresh_button.clicked.connect(self.refresh_view)
        header_layout.addWidget(refresh_button)
        main_layout.addLayout(header_layout)
        
                              
        message_frame = QFrame()
        message_frame.setStyleSheet(f"""
            QFrame {{
                background-color: #fff8e1;
                border-radius: 12px;
                padding: 20px;
                border: 1px solid #ffe082;
            }}
        """)
        message_layout = QVBoxLayout(message_frame)
        message_layout.setSpacing(8)
        
        message_title = QLabel("❤️ Spread Kindness")
        message_title.setStyleSheet("font-weight: 600; color: #e67e22; font-size: 16px;")
        
        message_text = QLabel("Every donation makes a difference! Remember to give within your means.\nYour generosity helps create positive change in the world.")
        message_text.setStyleSheet("color: #7f8c8d; font-size: 14px;")
        message_text.setWordWrap(True)
        
        message_layout.addWidget(message_title)
        message_layout.addWidget(message_text)
        
        main_layout.addWidget(message_frame)
        
                      
        balance_frame = QFrame()
        balance_frame.setStyleSheet(Styles.get_card_style())
        balance_layout = QVBoxLayout(balance_frame)
        balance_layout.setSpacing(12)
        
        balance_title = QLabel("Available Balance")
        balance_title.setStyleSheet(Styles.get_subtitle())
        
        self.balance_label = QLabel("$0.00")
        self.balance_label.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        self.balance_label.setStyleSheet(f"color: {Styles.WARNING_COLOR};")
        
        self.balance_warning = QLabel("")
        self.balance_warning.setStyleSheet(f"color: {Styles.DANGER_COLOR}; font-weight: 600; padding: 8px; border-radius: 6px; background-color: #ffeaea;")
        self.balance_warning.hide()
        
        balance_layout.addWidget(balance_title)
        balance_layout.addWidget(self.balance_label)
        balance_layout.addWidget(self.balance_warning)
        
        main_layout.addWidget(balance_frame)
        
              
        form_frame = QFrame()
        form_frame.setStyleSheet(Styles.get_card_style())
        form_layout = QFormLayout(form_frame)
        form_layout.setVerticalSpacing(20)
        form_layout.setHorizontalSpacing(24)
        form_layout.setContentsMargins(24, 24, 24, 24)
        
                
        self.amount_input = QDoubleSpinBox()
        self.amount_input.setRange(AppConstants.MIN_AMOUNT, AppConstants.MAX_AMOUNT)
        self.amount_input.setPrefix("$ ")
        self.amount_input.setDecimals(2)
        self.amount_input.setValue(AppConstants.MIN_AMOUNT)
        self.amount_input.valueChanged.connect(self.check_balance)
        self.amount_input.setStyleSheet(Styles.get_input_style())
        
                  
        self.category_combo = QComboBox()
        self.category_combo.setStyleSheet(Styles.get_input_style())
        self.load_categories()
        
                     
        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("e.g., Local food bank, Animal shelter, etc.")
        self.description_input.setStyleSheet(Styles.get_input_style())

        self.repeat_check = QComboBox()
        self.repeat_check.addItem("No", False)
        self.repeat_check.addItem("Yes", True)
        self.repeat_check.setStyleSheet(Styles.get_input_style())
        self.repeat_every = QSpinBox()
        self.repeat_every.setRange(1, 365)
        self.repeat_every.setValue(1)
        self.repeat_every.setStyleSheet(Styles.get_input_style())
        self.repeat_unit = QComboBox()
        self.repeat_unit.addItems(["Days", "Weeks", "Months"])
        self.repeat_unit.setStyleSheet(Styles.get_input_style())
        self.repeat_start = QDateEdit()
        self.repeat_start.setDate(QDate.currentDate())
        self.repeat_start.setCalendarPopup(True)
        self.repeat_start.setStyleSheet(Styles.get_input_style())
        self.repeat_every_label = QLabel("Repeat every:")
        self.repeat_start_label = QLabel("Start date:")
        repeat_row = QHBoxLayout()
        repeat_row.setSpacing(10)
        repeat_row.addWidget(self.repeat_every)
        repeat_row.addWidget(self.repeat_unit)

        form_layout.addRow(QLabel("Donation Amount:"), self.amount_input)
        form_layout.addRow(QLabel("Category:"), self.category_combo)
        form_layout.addRow(QLabel("Description:"), self.description_input)
        form_layout.addRow(QLabel("Auto repeat:"), self.repeat_check)
        form_layout.addRow(self.repeat_every_label, repeat_row)
        form_layout.addRow(self.repeat_start_label, self.repeat_start)
        self.repeat_check.currentIndexChanged.connect(self._update_repeat_controls)
        self._update_repeat_controls()
        
        main_layout.addWidget(form_frame)
        
                         
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.donate_button = QPushButton("❤️ Make Donation")
        self.donate_button.clicked.connect(self.add_donation)
        self.donate_button.setStyleSheet(Styles.get_warning_button())
        self.donate_button.setMinimumWidth(200)
        button_layout.addWidget(self.donate_button)
        button_layout.addStretch()
        
        main_layout.addLayout(button_layout)
        
                        
        goals_frame = QFrame()
        goals_frame.setStyleSheet(Styles.get_card_style())
        goals_layout = QVBoxLayout(goals_frame)
        goals_layout.setSpacing(16)
        
        goals_title = QLabel("🎯 Donation Goals Progress")
        goals_title.setStyleSheet(Styles.get_subtitle())
        goals_layout.addWidget(goals_title)
        
        self.goals_container = QVBoxLayout()
        self.goals_container.setSpacing(12)
        goals_layout.addLayout(self.goals_container)
        
        main_layout.addWidget(goals_frame)
        
                                           
        main_layout.addStretch()
        
        scroll_area.setWidget(container)
        
                    
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_area)
        
                                              
        self.update_balance()
        self.check_balance()
        self.load_goals()

    def refresh_view(self):
        """Refresh visible data in this tab."""
        self.load_categories()
        self.update_balance()
        self.check_balance()
        self.load_goals()
    
    def load_categories(self):
        """Load donation categories into the combo box"""
        self.category_combo.clear()
        categories = self.db.get_categories('donation')
        
        if not categories:
                                                           
            for name, color, icon in DEFAULT_DONATION_CATEGORIES:
                self.category_combo.addItem(f"{icon} {name}", -1)
        else:
            for cat in categories:
                self.category_combo.addItem(f"{cat['icon']} {cat['name']}", cat['id'])
        
    def update_balance(self):
        """Update the balance display"""
        current_balance = self.db.get_current_balance()
        self.balance_label.setText(f"${current_balance:,.2f}")
        
    def check_balance(self):
        """Check if donation amount exceeds balance"""
        amount = self.amount_input.value()
        current_balance = self.db.get_current_balance()
        
        if amount > current_balance:
            self.balance_warning.setText(
                f"⚠️ Adjust donation amount\n"
                f"Donation: ${amount:,.2f} | Available: ${current_balance:,.2f}"
            )
            self.balance_warning.show()
            self.donate_button.setEnabled(False)
            self.donate_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Styles.GRAY_COLOR};
                    color: white;
                    border: none;
                    padding: 14px 28px;
                    border-radius: 8px;
                    font-weight: 600;
                    font-size: 15px;
                    min-height: 48px;
                }}
            """)
        else:
            self.balance_warning.hide()
            self.donate_button.setEnabled(True)
            self.donate_button.setStyleSheet(Styles.get_warning_button())
            
    def load_goals(self):
        """Load and display donation goals"""
                              
        for i in reversed(range(self.goals_container.count())):
            widget = self.goals_container.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        
        goals = self.db.get_donation_goals()
        
        if not goals:
            empty_label = QLabel("No active donation goals. Create one in the Goals tab!")
            empty_label.setStyleSheet("color: #95a5a6; font-style: italic; font-size: 14px; padding: 20px;")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.goals_container.addWidget(empty_label)
        else:
            for goal in goals:
                goal_widget = self.create_goal_widget(goal)
                self.goals_container.addWidget(goal_widget)
        
        self.goals_container.addStretch()
        
    def create_goal_widget(self, goal):
        """Create a widget for a donation goal"""
        widget = QFrame()
        widget.setStyleSheet("""
            QFrame {
                border: 1px solid #e9ecef;
                border-radius: 8px;
                padding: 16px;
            }
        """)
        
        layout = QVBoxLayout(widget)
        layout.setSpacing(8)
        
                                
        name_layout = QHBoxLayout()
        name_label = QLabel(goal['name'])
        name_label.setStyleSheet("font-weight: 600; color: #2c3e50; font-size: 14px;")
        
        progress_text = QLabel(f"${goal['current_amount']:,.2f} / ${goal['target_amount']:,.2f}")
        progress_text.setStyleSheet("color: #6c757d; font-size: 13px;")
        
        name_layout.addWidget(name_label)
        name_layout.addStretch()
        name_layout.addWidget(progress_text)
        
                      
        progress_bar = QProgressBar()
        progress_bar.setRange(0, int(AppConstants.PROGRESS_MAX))
        progress_bar.setValue(int(clamp_percentage(goal['progress'])))
        progress_bar.setFormat(f"{goal['progress']:.1f}% Complete")
        progress_bar.setStyleSheet(Styles.get_progress_bar())
        
        layout.addLayout(name_layout)
        layout.addWidget(progress_bar)
        
        return widget
    
    def add_donation(self):
        """Add donation transaction"""
        amount = self.amount_input.value()
        category_id = self.category_combo.currentData()
        category_text = self.category_combo.currentText()
        description = self.description_input.text().strip()

        if amount <= 0:
            QMessageBox.warning(self, "Invalid Amount", "Please enter a positive amount.")
            return

                          
        reply = QMessageBox.question(
            self, "Confirm Donation",
            f"Are you sure you want to donate ${amount:,.2f}\n\n"
            "Thank you for your generosity! ",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            result = self.service.add_donation(amount, category_id, category_text, description)

            if result.created_category:
                self.load_categories()

            if result.success:
                if self.repeat_check.currentData():
                    scheduled = self.db.add_recurring_transaction(
                        "donation",
                        amount,
                        result.category_id,
                        description,
                        self.repeat_start.date().toString("yyyy-MM-dd"),
                        self.repeat_every.value(),
                        self._repeat_unit_to_db(self.repeat_unit.currentText())
                    )
                    if not scheduled:
                        QMessageBox.warning(self, "Warning", "Donation added, but failed to create recurring schedule.")
                show_toast(
                    self,
                    f"Thank you for your donation of ${amount:,.2f}! Your generosity makes a difference.",
                    level="success",
                    duration_ms=3500
                )
                self.clear_form()
                self.update_balance()
                self.transaction_added.emit()
                self.load_goals()                          
            else:
                if "positive amount" in result.message.lower():
                    QMessageBox.warning(self, "Invalid Amount", result.message)
                else:
                    QMessageBox.critical(self, "Error", result.message)

    def clear_form(self):
        """Clear the form inputs"""
        self.amount_input.setValue(AppConstants.MIN_AMOUNT)
        self.description_input.clear()
        self.repeat_check.setCurrentIndex(0)
        self.check_balance()

    def _repeat_unit_to_db(self, text):
        mapping = {"Days": "day", "Weeks": "week", "Months": "month"}
        return mapping.get(text, "month")

    def _update_repeat_controls(self, *_):
        enabled = bool(self.repeat_check.currentData())
        self.repeat_every_label.setVisible(enabled)
        self.repeat_every.setVisible(enabled)
        self.repeat_every.setEnabled(enabled)
        self.repeat_unit.setVisible(enabled)
        self.repeat_unit.setEnabled(enabled)
        self.repeat_start_label.setVisible(enabled)
        self.repeat_start.setVisible(enabled)
        self.repeat_start.setEnabled(enabled)


class CircularProgressRing(QWidget):
    """Simple circular progress ring widget."""

    def __init__(self, progress=0.0, color=Styles.SUCCESS_COLOR, parent=None):
        super().__init__(parent)
        self.progress = clamp_percentage(progress)
        self.color = QColor(color)
        self.setMinimumSize(92, 92)
        self.setMaximumSize(92, 92)

    def set_progress(self, progress, color=None):
        self.progress = clamp_percentage(progress)
        if color:
            self.color = QColor(color)
        self.update()

    def sizeHint(self):
        return QSize(92, 92)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(8, 8, -8, -8)

        track_pen = QPen(QColor("#e9ecef"), 8)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(rect, 0, 360 * 16)

        value_pen = QPen(self.color, 8)
        value_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(value_pen)
        span = int(360 * 16 * (self.progress / 100.0))
        painter.drawArc(rect, 90 * 16, -span)

        painter.setPen(QColor("#2c3e50"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"{self.progress:.0f}%")

class GoalsView(QWidget):
    """View for managing personal and donation goals."""
    
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.service = FinanceService(db)
        self.setup_ui()
        self.load_goals()
        
    def setup_ui(self):
                                                
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("border: none; background: transparent;")
        
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(28)
        main_layout.setContentsMargins(32, 24, 32, 40)                      
        
                
        header_layout = QHBoxLayout()
        
        title = QLabel("🎯 Goals and Savings")
        title.setStyleSheet(Styles.get_section_title())
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
                        
        set_income_button = QPushButton("💵 Set Monthly Income")
        set_income_button.setStyleSheet(Styles.get_secondary_button())
        set_income_button.clicked.connect(self.show_income_dialog)
        header_layout.addWidget(set_income_button)

        refresh_button = QPushButton("🔄 Refresh")
        refresh_button.setStyleSheet(Styles.get_secondary_button())
        refresh_button.clicked.connect(self.refresh_view)
        header_layout.addWidget(refresh_button)
        
        main_layout.addLayout(header_layout)
        
                                                                 
        stats_frame = self.create_stats_frame()
        main_layout.addWidget(stats_frame)

                        
        savings_frame = QFrame()
        savings_frame.setStyleSheet(Styles.get_card_style())
        savings_layout = QVBoxLayout(savings_frame)
        savings_layout.setSpacing(12)

        savings_title = QLabel("💰 Savings Planner")
        savings_title.setStyleSheet(Styles.get_subtitle())
        savings_layout.addWidget(savings_title)

        self.goals_savings_guide = QLabel("")
        self.goals_savings_guide.setWordWrap(True)
        self.goals_savings_guide.setStyleSheet("color: #2c3e50; font-size: 14px;")
        savings_layout.addWidget(self.goals_savings_guide)

        self.goals_savings_result = QLabel("")
        self.goals_savings_result.setWordWrap(True)
        self.goals_savings_result.setStyleSheet("color: #2c3e50; font-size: 14px; font-weight: 600;")
        savings_layout.addWidget(self.goals_savings_result)

                            
        calc_frame = QFrame()
        calc_frame.setStyleSheet(Styles.get_card_style())
        calc_layout = QVBoxLayout(calc_frame)
        calc_layout.setSpacing(12)

        calc_title = QLabel("Savings Calculator")
        calc_title.setStyleSheet(Styles.get_subtitle())
        calc_layout.addWidget(calc_title)

        calc_form = QFormLayout()
        calc_form.setHorizontalSpacing(12)
        calc_form.setVerticalSpacing(12)

        self.goal_calc_mode = QComboBox()
        self.goal_calc_mode.addItems([
            "How much will I save?",
            "How long until I reach a target?",
            "How much do I need to save?"
        ])
        self.goal_calc_mode.setStyleSheet(Styles.get_input_style())

        self.goal_calc_amount = QDoubleSpinBox()
        self.goal_calc_amount.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        self.goal_calc_amount.setPrefix("$ ")
        self.goal_calc_amount.setRange(AppConstants.MIN_AMOUNT, AppConstants.MAX_AMOUNT)
        self.goal_calc_amount.setValue(AppConstants.DEFAULT_BUDGET_AMOUNT)
        self.goal_calc_amount.setStyleSheet(Styles.get_input_style())

        self.goal_calc_period = QSpinBox()
        self.goal_calc_period.setRange(1, 600)
        self.goal_calc_period.setValue(12)
        self.goal_calc_period.setStyleSheet(Styles.get_input_style())

        self.goal_calc_unit = QComboBox()
        self.goal_calc_unit.addItems(["Months", "Years"])
        self.goal_calc_unit.setStyleSheet(Styles.get_input_style())

        self.goal_calc_rate = QDoubleSpinBox()
        self.goal_calc_rate.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        self.goal_calc_rate.setSuffix("%")
        self.goal_calc_rate.setRange(0, 20)
        self.goal_calc_rate.setDecimals(2)
        self.goal_calc_rate.setValue(AppConstants.SAVINGS_PROJECTION_RATE * 100)
        self.goal_calc_rate.setStyleSheet(Styles.get_input_style())

        self.goal_calc_target = QDoubleSpinBox()
        self.goal_calc_target.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        self.goal_calc_target.setPrefix("$ ")
        self.goal_calc_target.setRange(AppConstants.MIN_AMOUNT, AppConstants.MAX_AMOUNT)
        self.goal_calc_target.setValue(5000.00)
        self.goal_calc_target.setStyleSheet(Styles.get_input_style())

        self.goal_calc_monthly = QDoubleSpinBox()
        self.goal_calc_monthly.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        self.goal_calc_monthly.setPrefix("$ ")
        self.goal_calc_monthly.setRange(AppConstants.MIN_AMOUNT, AppConstants.MAX_AMOUNT)
        self.goal_calc_monthly.setValue(300.00)
        self.goal_calc_monthly.setStyleSheet(Styles.get_input_style())

        self.goal_calc_mode_label = QLabel("Mode:")
        self.goal_calc_save_label = QLabel("Save Amount:")
        self.goal_calc_period_label = QLabel("Period:")
        self.goal_calc_unit_label = QLabel("Period Unit:")
        self.goal_calc_growth_label = QLabel("Annual Growth:")
        self.goal_calc_target_label = QLabel("Target Amount:")
        self.goal_calc_monthly_label = QLabel("Save Per Month:")

        calc_form.addRow(self.goal_calc_mode_label, self.goal_calc_mode)
        calc_form.addRow(self.goal_calc_save_label, self.goal_calc_amount)
        calc_form.addRow(self.goal_calc_period_label, self.goal_calc_period)
        calc_form.addRow(self.goal_calc_unit_label, self.goal_calc_unit)
        calc_form.addRow(self.goal_calc_growth_label, self.goal_calc_rate)
        calc_form.addRow(self.goal_calc_target_label, self.goal_calc_target)
        calc_form.addRow(self.goal_calc_monthly_label, self.goal_calc_monthly)
        calc_layout.addLayout(calc_form)

        self.goal_calc_result = QLabel("")
        self.goal_calc_result.setStyleSheet("font-weight: 600; color: #2c3e50; font-size: 14px;")
        self.goal_calc_result.setWordWrap(True)
        calc_layout.addWidget(self.goal_calc_result)
        
                              
        create_frame = QFrame()
        create_frame.setStyleSheet(Styles.get_card_style())
        create_layout = QVBoxLayout(create_frame)
        create_layout.setSpacing(20)
        
        create_title = QLabel("➕ Create New Goal")
        create_title.setStyleSheet(Styles.get_subtitle())
        create_layout.addWidget(create_title)

        type_layout = QVBoxLayout()
        type_layout.setSpacing(8)
        type_layout.addWidget(QLabel("Goal Type:"))
        self.goal_type_combo = QComboBox()
        self.goal_type_combo.addItem("Dream Goal", "dream")
        self.goal_type_combo.addItem("Donation Goal", "donation")
        self.goal_type_combo.setStyleSheet(Styles.get_input_style())
        self.goal_type_combo.currentIndexChanged.connect(self.update_goal_name_placeholder)
        type_layout.addWidget(self.goal_type_combo)
        create_layout.addLayout(type_layout)
        
                   
        name_layout = QVBoxLayout()
        name_layout.setSpacing(8)
        name_layout.addWidget(QLabel("Goal Name:"))
        
        self.goal_name_input = QLineEdit()
        self.goal_name_input.setPlaceholderText("e.g., Dream House, Dream Car, Travel Fund")
        self.goal_name_input.setStyleSheet(Styles.get_input_style())
        name_layout.addWidget(self.goal_name_input)
        create_layout.addLayout(name_layout)
        
                       
        target_layout = QVBoxLayout()
        target_layout.setSpacing(8)
        target_layout.addWidget(QLabel("Target Amount:"))
        
        self.target_amount_input = QDoubleSpinBox()
        self.target_amount_input.setPrefix("$ ")
        self.target_amount_input.setRange(AppConstants.MIN_AMOUNT, AppConstants.MAX_AMOUNT)
        self.target_amount_input.setValue(AppConstants.DEFAULT_GOAL_TARGET)
        self.target_amount_input.setStyleSheet(Styles.get_input_style())
        target_layout.addWidget(self.target_amount_input)
        create_layout.addLayout(target_layout)

        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(8)
        progress_layout.addWidget(QLabel("Current Progress (optional):"))
        self.current_progress_input = QDoubleSpinBox()
        self.current_progress_input.setPrefix("$ ")
        self.current_progress_input.setRange(0, AppConstants.MAX_AMOUNT)
        self.current_progress_input.setValue(0.00)
        self.current_progress_input.setStyleSheet(Styles.get_input_style())
        progress_layout.addWidget(self.current_progress_input)
        create_layout.addLayout(progress_layout)

        self.auto_save_check = QCheckBox("Enable auto-save for this goal")
        self.auto_save_check.setStyleSheet("font-size: 13px; color: #2c3e50;")
        create_layout.addWidget(self.auto_save_check)

        auto_amount_layout = QVBoxLayout()
        auto_amount_layout.setSpacing(8)
        self.auto_save_amount_label = QLabel("Auto-save amount:")
        auto_amount_layout.addWidget(self.auto_save_amount_label)
        self.auto_save_amount_input = QDoubleSpinBox()
        self.auto_save_amount_input.setPrefix("$ ")
        self.auto_save_amount_input.setRange(AppConstants.MIN_AMOUNT, AppConstants.MAX_AMOUNT)
        self.auto_save_amount_input.setValue(50.00)
        self.auto_save_amount_input.setStyleSheet(Styles.get_input_style())
        auto_amount_layout.addWidget(self.auto_save_amount_input)
        create_layout.addLayout(auto_amount_layout)

        auto_repeat_layout = QVBoxLayout()
        auto_repeat_layout.setSpacing(8)
        self.auto_save_interval_label = QLabel("Auto-save interval:")
        auto_repeat_layout.addWidget(self.auto_save_interval_label)
        auto_repeat_row = QHBoxLayout()
        auto_repeat_row.setSpacing(10)
        self.auto_save_every = QSpinBox()
        self.auto_save_every.setRange(1, 365)
        self.auto_save_every.setValue(1)
        self.auto_save_every.setStyleSheet(Styles.get_input_style())
        self.auto_save_unit = QComboBox()
        self.auto_save_unit.addItems(["Days", "Weeks", "Months"])
        self.auto_save_unit.setStyleSheet(Styles.get_input_style())
        auto_repeat_row.addWidget(self.auto_save_every)
        auto_repeat_row.addWidget(self.auto_save_unit)
        auto_repeat_layout.addLayout(auto_repeat_row)
        create_layout.addLayout(auto_repeat_layout)

        auto_start_layout = QVBoxLayout()
        auto_start_layout.setSpacing(8)
        self.auto_save_start_label = QLabel("Auto-save start date:")
        auto_start_layout.addWidget(self.auto_save_start_label)
        self.auto_save_start = QDateEdit()
        self.auto_save_start.setDate(QDate.currentDate())
        self.auto_save_start.setCalendarPopup(True)
        self.auto_save_start.setStyleSheet(Styles.get_input_style())
        auto_start_layout.addWidget(self.auto_save_start)
        create_layout.addLayout(auto_start_layout)
        self.auto_save_check.toggled.connect(self._update_auto_save_controls)
        self._update_auto_save_controls(False)
        
                  
        deadline_layout = QVBoxLayout()
        deadline_layout.setSpacing(8)
        deadline_layout.addWidget(QLabel("Target Date:"))
        
        self.deadline_input = QDateEdit()
        self.deadline_input.setDate(QDate.currentDate().addMonths(1))
        self.deadline_input.setCalendarPopup(True)
        self.deadline_input.setMinimumDate(QDate.currentDate())
        self.deadline_input.setStyleSheet(Styles.get_input_style())
        deadline_layout.addWidget(self.deadline_input)
        create_layout.addLayout(deadline_layout)
        
                       
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        create_button = QPushButton("🎯 Create Goal")
        create_button.clicked.connect(self.create_goal)
        create_button.setStyleSheet(Styles.get_success_button())
        create_button.setMinimumWidth(180)
        button_layout.addWidget(create_button)
        button_layout.addStretch()
        
        create_layout.addLayout(button_layout)
        
        main_layout.addWidget(create_frame)
        
                                              
        list_frame = QFrame()
        list_frame.setStyleSheet(Styles.get_card_style())
        list_layout = QVBoxLayout(list_frame)
        list_layout.setSpacing(16)
        
        list_title = QLabel("📋 Your Active Goals")
        list_title.setStyleSheet(Styles.get_subtitle())
        list_layout.addWidget(list_title)
        
                                                                  
        self.goals_container = QVBoxLayout()
        self.goals_container.setSpacing(16)
        list_layout.addLayout(self.goals_container)
        
        main_layout.addWidget(list_frame)
        main_layout.addWidget(savings_frame)
        main_layout.addWidget(calc_frame)
        
                                           
        main_layout.addStretch()
        
        scroll_area.setWidget(container)
        
                    
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_area)
        self.update_goal_name_placeholder()
        self.update_savings_helper()
        self.goal_calc_amount.valueChanged.connect(self.update_goal_savings_calculator)
        self.goal_calc_period.valueChanged.connect(self.update_goal_savings_calculator)
        self.goal_calc_unit.currentIndexChanged.connect(self.update_goal_savings_calculator)
        self.goal_calc_rate.valueChanged.connect(self.update_goal_savings_calculator)
        self.goal_calc_target.valueChanged.connect(self.update_goal_savings_calculator)
        self.goal_calc_monthly.valueChanged.connect(self.update_goal_savings_calculator)
        self.goal_calc_mode.currentIndexChanged.connect(self.update_goal_calculator_mode)
        self.update_goal_calculator_mode()
        self.update_goal_savings_calculator()
        
    def create_stats_frame(self):
        """Create a stats frame showing goal progress - FIXED: Create only once"""
        frame = QFrame()
        frame.setStyleSheet(Styles.get_card_style())
        layout = QVBoxLayout(frame)
        layout.setSpacing(16)
        
        stats_title = QLabel("📊 Goal Statistics")
        stats_title.setStyleSheet(Styles.get_subtitle())
        layout.addWidget(stats_title)
        
                                                            
        self.stats_grid = QGridLayout()
        self.stats_grid.setSpacing(12)
        
                                                                
                     
        total_label = QLabel("Total Goals:")
        total_label.setStyleSheet("color: #6c757d; font-size: 14px;")
        self.total_value = QLabel("0")
        self.total_value.setStyleSheet("font-weight: 600; color: #2c3e50; font-size: 16px;")
        self.stats_grid.addWidget(total_label, 0, 0)
        self.stats_grid.addWidget(self.total_value, 0, 1)
        
                         
        completed_label = QLabel("Completed:")
        completed_label.setStyleSheet("color: #6c757d; font-size: 14px;")
        self.completed_value = QLabel("0")
        self.completed_value.setStyleSheet(f"font-weight: 600; color: {Styles.SUCCESS_COLOR}; font-size: 16px;")
        self.stats_grid.addWidget(completed_label, 0, 2)
        self.stats_grid.addWidget(self.completed_value, 0, 3)
        
                      
        target_label = QLabel("Total Target:")
        target_label.setStyleSheet("color: #6c757d; font-size: 14px;")
        self.target_value = QLabel("$0.00")
        self.target_value.setStyleSheet("font-weight: 600; color: #3498db; font-size: 16px;")
        self.stats_grid.addWidget(target_label, 1, 0)
        self.stats_grid.addWidget(self.target_value, 1, 1)
        
                      
        raised_label = QLabel("Total Achieved:")
        raised_label.setStyleSheet("color: #6c757d; font-size: 14px;")
        self.raised_value = QLabel("$0.00")
        self.raised_value.setStyleSheet("font-weight: 600; color: #e67e22; font-size: 16px;")
        self.stats_grid.addWidget(raised_label, 1, 2)
        self.stats_grid.addWidget(self.raised_value, 1, 3)
        
                            
        upcoming_label = QLabel("Upcoming (7 days):")
        upcoming_label.setStyleSheet("color: #6c757d; font-size: 14px;")
        self.upcoming_value = QLabel("0")
        self.upcoming_value.setStyleSheet(f"font-weight: 600; color: {Styles.WARNING_COLOR}; font-size: 16px;")
        self.stats_grid.addWidget(upcoming_label, 2, 0)
        self.stats_grid.addWidget(self.upcoming_value, 2, 1)
        
                        
        past_label = QLabel("Past Due:")
        past_label.setStyleSheet("color: #6c757d; font-size: 14px;")
        self.past_value = QLabel("0")
        self.past_value.setStyleSheet(f"font-weight: 600; color: {Styles.DANGER_COLOR}; font-size: 16px;")
        self.stats_grid.addWidget(past_label, 2, 2)
        self.stats_grid.addWidget(self.past_value, 2, 3)
        
        layout.addLayout(self.stats_grid)
        
                              
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, int(AppConstants.PROGRESS_MAX))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Overall Progress: 0.0%")
        self.progress_bar.setStyleSheet(Styles.get_progress_bar())
        layout.addWidget(self.progress_bar)
        
        return frame
    
    def update_stats(self, goals):
        """Update the stats display - FIXED: Only update values, don't recreate widgets"""
        if not goals:
                                      
            self.total_value.setText("0")
            self.completed_value.setText("0")
            self.target_value.setText("$0.00")
            self.raised_value.setText("$0.00")
            self.upcoming_value.setText("0")
            self.past_value.setText("0")
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Overall Progress: 0.0%")
            return
        
                         
        total_goals = len(goals)
        total_target = sum(g['target_amount'] for g in goals)
        total_raised = sum(g['current_amount'] for g in goals)
        completed_goals = sum(1 for g in goals if g['current_amount'] >= g['target_amount'])
        
        today = date.today()
        upcoming_deadlines = 0
        past_deadlines = 0
        
        for goal in goals:
            try:
                deadline_date = datetime.strptime(goal['deadline_date'], "%Y-%m-%d").date()
                days_left = (deadline_date - today).days
                if days_left < 0:
                    past_deadlines += 1
                elif days_left <= 7:
                    upcoming_deadlines += 1
            except (TypeError, ValueError, KeyError):
                continue
        
                                                            
        self.total_value.setText(str(total_goals))
        self.completed_value.setText(str(completed_goals))
        self.target_value.setText(f"${total_target:,.2f}")
        self.raised_value.setText(f"${total_raised:,.2f}")
        self.upcoming_value.setText(str(upcoming_deadlines))
        self.past_value.setText(str(past_deadlines))
        
                                     
        overall_progress = (total_raised / total_target * 100) if total_target > 0 else 0
        self.progress_bar.setValue(int(clamp_percentage(overall_progress)))
        self.progress_bar.setFormat(f"Overall Progress: {overall_progress:.1f}%")
            
    def create_goal(self):
        """Create a new donation goal"""
        name = self.goal_name_input.text().strip()
        target = self.target_amount_input.value()
        current_progress = self.current_progress_input.value()
        goal_type = self.goal_type_combo.currentData()
        deadline = self.deadline_input.date().toString("yyyy-MM-dd")
        
        if not name:
            QMessageBox.warning(self, "Missing Information", "Please enter a goal name.")
            return
        
        if target <= 0:
            QMessageBox.warning(self, "Invalid Amount", "Please enter a positive target amount.")
            return

        if current_progress < 0:
            QMessageBox.warning(self, "Invalid Amount", "Progress cannot be negative.")
            return
        
        goal_id = self.db.create_goal(
            name=name,
            target_amount=target,
            deadline_date=deadline,
            goal_type=goal_type,
            current_amount=current_progress
        )
        
        if goal_id:
            if self.auto_save_check.isChecked():
                auto_saved = self.db.add_recurring_goal_save(
                    goal_id=goal_id,
                    amount=self.auto_save_amount_input.value(),
                    start_date=self.auto_save_start.date().toString("yyyy-MM-dd"),
                    interval_value=self.auto_save_every.value(),
                    interval_unit=self._repeat_unit_to_db(self.auto_save_unit.currentText())
                )
                if not auto_saved:
                    QMessageBox.warning(self, "Warning", "Goal created, but auto-save schedule failed to save.")
            show_toast(self, f"Goal '{name}' created successfully! 🎯", level="success")
            self.clear_form()
            self.load_goals()
        else:
            QMessageBox.critical(self, "Error", "Failed to create goal.")
            
    def clear_form(self):
        """Clear the form inputs"""
        self.goal_name_input.clear()
        self.goal_type_combo.setCurrentIndex(0)
        self.target_amount_input.setValue(AppConstants.DEFAULT_GOAL_TARGET)
        self.current_progress_input.setValue(0.00)
        self.auto_save_check.setChecked(False)
        self.auto_save_amount_input.setValue(50.00)
        self.auto_save_every.setValue(1)
        self.auto_save_unit.setCurrentIndex(2)
        self.auto_save_start.setDate(QDate.currentDate())
        self.deadline_input.setDate(QDate.currentDate().addMonths(1))

    def update_goal_name_placeholder(self):
        """Set goal name placeholder based on selected goal type."""
        goal_type = self.goal_type_combo.currentData()
        if goal_type == "donation":
            self.goal_name_input.setPlaceholderText(
                "e.g., Monthly Charity, Animal Shelter Fund, Emergency Relief"
            )
        else:
            self.goal_name_input.setPlaceholderText(
                "e.g., Dream House, Dream Car, Travel Fund"
            )

    def _repeat_unit_to_db(self, text):
        mapping = {"Days": "day", "Weeks": "week", "Months": "month"}
        return mapping.get(text, "month")

    def _update_auto_save_controls(self, enabled):
        self.auto_save_amount_label.setVisible(enabled)
        self.auto_save_amount_input.setEnabled(enabled)
        self.auto_save_amount_input.setVisible(enabled)
        self.auto_save_interval_label.setVisible(enabled)
        self.auto_save_every.setEnabled(enabled)
        self.auto_save_every.setVisible(enabled)
        self.auto_save_unit.setEnabled(enabled)
        self.auto_save_unit.setVisible(enabled)
        self.auto_save_start_label.setVisible(enabled)
        self.auto_save_start.setEnabled(enabled)
        self.auto_save_start.setVisible(enabled)

    def refresh_view(self):
        """Refresh visible data in this tab."""
        self.load_goals()
        self.update_savings_helper()
        self.update_goal_savings_calculator()

    def show_income_dialog(self):
        """Show dialog to set monthly income and refresh savings helpers."""
        dialog = IncomeSettingDialog(self.db, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_income = dialog.get_income()
            if self.db.set_monthly_income(new_income):
                self.update_savings_helper()
                self.update_goal_savings_calculator()
                show_toast(self, f"Monthly income set to ${new_income:,.2f}", level="success")
            else:
                QMessageBox.critical(self, "Error", "Failed to update monthly income.")

    def update_savings_helper(self):
        """Update savings helper text with user-specific numbers."""
        monthly_income = self.db.get_monthly_income()
        if monthly_income <= 0:
            self.goals_savings_guide.setText(
                "Set monthly income first to get personalized savings guidance."
            )
            self.goals_savings_result.setText("")
            return

        suggested = self.service.savings_guidance(monthly_income, AppConstants.SAVINGS_GUIDE_RATE)
        one_year = self.service.savings_projection(
            suggested, AppConstants.SAVINGS_PROJECTION_RATE, 12, is_years=False
        )
        self.goals_savings_guide.setText(
            f"Suggested monthly savings: ${suggested:,.2f} "
            f"({AppConstants.SAVINGS_GUIDE_RATE*100:.0f}% of your monthly income ${monthly_income:,.2f})."
        )
        self.goals_savings_result.setText(
            f"If you keep this pace, projected value after 12 months is about "
            f"${one_year:,.2f} at {AppConstants.SAVINGS_PROJECTION_RATE*100:.0f}% annual growth."
        )

    def update_goal_savings_calculator(self):
        """Update Goals tab savings calculator result."""
        amount = self.goal_calc_amount.value()
        periods = self.goal_calc_period.value()
        is_years = self.goal_calc_unit.currentText() == "Years"
        annual_rate = self.goal_calc_rate.value() / 100
        target_amount = self.goal_calc_target.value()
        monthly_save = self.goal_calc_monthly.value()

        total_no_growth = self.service.savings_projection(amount, 0, periods, is_years=is_years)
        total_with_growth = self.service.savings_projection(amount, annual_rate, periods, is_years=is_years)
        mode = self.goal_calc_mode.currentIndex()

        if mode == 0:
            label_period = "years" if is_years else "months"
            if annual_rate > 0:
                self.goal_calc_result.setText(
                    f"If you save ${amount:.2f} for {periods} {label_period}, "
                    f"you would have about ${total_no_growth:.2f} without growth, "
                    f"or ${total_with_growth:.2f} at {self.goal_calc_rate.value():.2f}% annual growth."
                )
            else:
                self.goal_calc_result.setText(
                    f"If you save ${amount:.2f} for {periods} {label_period}, "
                    f"you would have about ${total_no_growth:.2f}."
                )
            return

        months_needed = self.service.months_to_reach_target(target_amount, monthly_save, annual_rate)
        if mode == 1:
            if months_needed is None:
                self.goal_calc_result.setText(
                    f"Target planner: cannot reach ${target_amount:.2f} with ${monthly_save:.2f}/month "
                    f"within the configured horizon."
                )
                return

            years = months_needed // 12
            months = months_needed % 12
            if years > 0 and months > 0:
                duration_text = f"{years} years and {months} months"
            elif years > 0:
                duration_text = f"{years} years"
            else:
                duration_text = f"{months} months"

            self.goal_calc_result.setText(
                f"To reach ${target_amount:.2f} while saving ${monthly_save:.2f}/month, "
                f"estimated time is {duration_text} at {self.goal_calc_rate.value():.2f}% annual growth."
            )
            return

        required_monthly = self.service.required_monthly_saving(
            target_amount, periods, annual_rate, is_years=is_years
        )
        label_period = "years" if is_years else "months"
        self.goal_calc_result.setText(
            f"To reach ${target_amount:.2f} in {periods} {label_period}, "
            f"you need to save about ${required_monthly:.2f} per month "
            f"at {self.goal_calc_rate.value():.2f}% annual growth."
        )

    def update_goal_calculator_mode(self):
        """Show only calculator inputs relevant to selected mode."""
        mode = self.goal_calc_mode.currentIndex()
        save_mode = mode == 0
        target_time_mode = mode == 1
        required_save_mode = mode == 2

        self.goal_calc_save_label.setVisible(save_mode)
        self.goal_calc_amount.setVisible(save_mode)
        self.goal_calc_period_label.setVisible(save_mode or required_save_mode)
        self.goal_calc_period.setVisible(save_mode or required_save_mode)
        self.goal_calc_unit_label.setVisible(save_mode or required_save_mode)
        self.goal_calc_unit.setVisible(save_mode or required_save_mode)
        self.goal_calc_target_label.setVisible(target_time_mode or required_save_mode)
        self.goal_calc_target.setVisible(target_time_mode or required_save_mode)
        self.goal_calc_monthly_label.setVisible(target_time_mode)
        self.goal_calc_monthly.setVisible(target_time_mode)

        self.update_goal_savings_calculator()
        
    def load_goals(self):
        """Load and display goals as cards."""
                              
        for i in reversed(range(self.goals_container.count())):
            widget = self.goals_container.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        
        goals = self.db.get_goals()
        all_goals = self.db.get_all_goals()
        
                                                                          
        self.update_stats(all_goals)
        self.update_savings_helper()
        
        if not goals:
            empty_label = QLabel("🎯 No active goals. Create your first goal above!")
            empty_label.setStyleSheet("""
                color: #95a5a6;
                font-style: normal;
                font-size: 16px;
                font-family: 'Segoe UI', 'Segoe UI Emoji';
                padding: 40px;
                text-align: center;
            """)
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setWordWrap(True)
            self.goals_container.addWidget(empty_label)
        else:
            for goal in goals:
                goal_card = self.create_goal_card(goal)
                self.goals_container.addWidget(goal_card)
        
        self.goals_container.addStretch()
    
    def create_goal_card(self, goal):
        """Create a visual card for a goal"""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: white;
                border-radius: 12px;
                border: 2px solid #e9ecef;
                padding: 20px;
            }}
            QFrame:hover {{
                border-color: {Styles.PRIMARY_COLOR};
                box-shadow: 0 4px 12px rgba(52, 152, 219, 0.1);
            }}
        """)
        
        layout = QVBoxLayout(card)
        layout.setSpacing(16)
        
                     
        header_layout = QHBoxLayout()
        
                            
        name_layout = QVBoxLayout()
        name_layout.setSpacing(4)
        
        goal_type = goal.get('goal_type', 'dream')
        goal_icon = "🎯" if goal_type == "dream" else "❤️"
        goal_type_text = "Dream Goal" if goal_type == "dream" else "Donation Goal"

        name_label = QLabel(f"{goal_icon} {goal['name']}")
        name_label.setStyleSheet("font-weight: 600; color: #2c3e50; font-size: 18px;")
        name_layout.addWidget(name_label)
        
                      
        details_label = QLabel(
            f"{goal_type_text} | Target: ${goal['target_amount']:,.2f} | Progress: ${goal['current_amount']:,.2f}"
        )
        details_label.setStyleSheet("color: #6c757d; font-size: 14px;")
        name_layout.addWidget(details_label)
        
        header_layout.addLayout(name_layout)
        header_layout.addStretch()
        
                       
        deadline_layout = QVBoxLayout()
        deadline_layout.setAlignment(Qt.AlignmentFlag.AlignRight)
        days_left = None
        
        try:
            deadline_date = datetime.strptime(goal['deadline_date'], "%Y-%m-%d").date()
            today = date.today()
            days_left = (deadline_date - today).days
            
            if days_left < 0:
                deadline_text = f"⏰ {abs(days_left)} days overdue"
                deadline_color = Styles.DANGER_COLOR
            elif days_left == 0:
                deadline_text = "⏰ Due today!"
                deadline_color = Styles.WARNING_COLOR
            elif days_left <= 7:
                deadline_text = f"⏰ {days_left} days left"
                deadline_color = Styles.WARNING_COLOR
            else:
                deadline_text = f"📅 {days_left} days left"
                deadline_color = "#3498db"
                
            deadline_label = QLabel(deadline_text)
            deadline_label.setStyleSheet(f"font-weight: 600; color: {deadline_color}; font-size: 14px;")
            deadline_layout.addWidget(deadline_label)
            
        except (TypeError, ValueError, KeyError):
            deadline_label = QLabel(f"📅 {goal['deadline_date']}")
            deadline_label.setStyleSheet("color: #6c757d; font-size: 14px;")
            deadline_layout.addWidget(deadline_label)
        
        header_layout.addLayout(deadline_layout)
        layout.addLayout(header_layout)
        
                                     
        progress_row = QHBoxLayout()
        progress_row.setSpacing(16)

        if goal['progress'] >= AppConstants.PROGRESS_MAX:
            ring_color = Styles.SUCCESS_COLOR
        elif days_left is not None and days_left < 0:
            ring_color = Styles.DANGER_COLOR
        elif days_left is not None and days_left <= 7:
            ring_color = Styles.WARNING_COLOR
        elif goal['progress'] >= AppConstants.GOAL_PROGRESS_HALF:
            ring_color = Styles.SUCCESS_COLOR
        else:
            ring_color = Styles.WARNING_COLOR

        ring_col = QVBoxLayout()
        ring_col.setSpacing(6)
        ring_col.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        ring = CircularProgressRing(goal['progress'], ring_color)
        ring_col.addWidget(ring, alignment=Qt.AlignmentFlag.AlignHCenter)

        if days_left is None:
            days_text = "No deadline info"
        elif days_left < 0:
            days_text = f"{abs(days_left)} day(s) overdue"
        elif days_left == 0:
            days_text = "Due today"
        else:
            days_text = f"{days_left} day(s) left"

        days_label = QLabel(days_text)
        days_label.setStyleSheet("color: #6c757d; font-size: 12px;")
        days_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ring_col.addWidget(days_label)
        progress_row.addLayout(ring_col)

        details_col = QVBoxLayout()
        details_col.setSpacing(6)
        progress_text = QLabel(f"{goal['progress']:.1f}% Complete")
        progress_text.setStyleSheet("font-weight: 600; color: #2c3e50; font-size: 14px;")
        details_col.addWidget(progress_text)

        remaining_amount = max(0.0, goal['target_amount'] - goal['current_amount'])
        remaining_label = QLabel(f"Remaining: ${remaining_amount:,.2f}")
        remaining_label.setStyleSheet("color: #6c757d; font-size: 13px;")
        details_col.addWidget(remaining_label)
        details_col.addStretch()

        progress_row.addLayout(details_col, 1)
        layout.addLayout(progress_row)
        
                        
        action_layout = QHBoxLayout()
        
        add_progress_button = QPushButton("Save Some")
        add_progress_button.setToolTip("Save part of your current balance toward this goal")
        add_progress_button.setStyleSheet(Styles.get_primary_button())
        add_progress_button.clicked.connect(lambda checked, g=goal: self.add_goal_progress(g))

        achieve_button = QPushButton("Achieve Now")
        achieve_button.setToolTip("Contribute the remaining amount and complete this goal")
        achieve_button.setStyleSheet(Styles.get_success_button())
        achieve_button.clicked.connect(lambda checked, g=goal: self.achieve_goal(g))

                       
        delete_button = QPushButton("🗑️ Delete")
        delete_button.setToolTip("Delete this goal")
        delete_button.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {Styles.DANGER_COLOR};
                border-radius: 6px;
                padding: 8px 16px;
                color: {Styles.DANGER_COLOR};
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: #ffeaea;
            }}
        """)
        delete_button.clicked.connect(lambda checked, g=goal: self.delete_goal(g))
        
        action_layout.addStretch()
        action_layout.addWidget(add_progress_button)
        action_layout.addWidget(achieve_button)
        action_layout.addWidget(delete_button)
        
        layout.addLayout(action_layout)
        
        return card

    def add_goal_progress(self, goal):
        """Save part of the current balance toward the selected goal."""
        amount, ok = QInputDialog.getDouble(
            self,
            "Save Toward Goal",
            f"How much do you want to save toward '{goal['name']}'?",
            0.0,
            0.0,
            AppConstants.MAX_AMOUNT,
            2
        )
        if not ok:
            return
        if amount <= 0:
            QMessageBox.warning(self, "Invalid Amount", "Please enter an amount greater than zero.")
            return

        success, message = self.db.contribute_to_goal(goal['id'], amount)
        if success:
            show_toast(self, message, level="success")
            self.load_goals()
        else:
            QMessageBox.critical(self, "Error", message)

    def achieve_goal(self, goal):
        """Contribute the remaining amount and mark the goal complete."""
        remaining = max(0.0, goal['target_amount'] - goal['current_amount'])
        if remaining <= 0:
            if self.db.mark_goal_achieved(goal['id']):
                show_toast(self, f"Goal '{goal['name']}' marked as achieved.", level="success")
                self.load_goals()
            else:
                QMessageBox.critical(self, "Error", "Failed to mark goal as achieved.")
            return

        reply = QMessageBox.question(
            self,
            "Achieve Goal",
            f"Contribute ${remaining:,.2f} from your balance to complete '{goal['name']}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        success, message = self.db.contribute_to_goal(goal['id'], remaining)
        if success:
            show_toast(self, message, level="success")
            self.load_goals()
        else:
            QMessageBox.critical(self, "Error", message)
    
    def delete_goal(self, goal):
        """Delete a goal"""
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete the goal '{goal['name']}'",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            success = self.db.delete_goal(goal['id'])
            
            if success:
                show_toast(self, f"Goal '{goal['name']}' deleted successfully!", level="success")
                self.load_goals()
            else:
                QMessageBox.critical(self, "Error", "Failed to delete goal.")

class InsightsView(QWidget):
    """View for financial insights and education"""
    
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.service = FinanceService(db)
        self.setup_ui()
        self.load_insights()
        
    def setup_ui(self):
                                                
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("border: none;")
        
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(28)
        main_layout.setContentsMargins(32, 24, 32, 40)                      
        
                
        header_layout = QHBoxLayout()
        
        title = QLabel("Insights & Education")
        title.setStyleSheet(Styles.get_section_title())
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        refresh_button = QPushButton("🔄 Refresh")
        refresh_button.setStyleSheet(Styles.get_secondary_button())
        refresh_button.clicked.connect(self.load_insights)
        header_layout.addWidget(refresh_button)
        
        main_layout.addLayout(header_layout)
        
                        
        tips_frame = QFrame()
        tips_frame.setStyleSheet(Styles.get_card_style())
        tips_layout = QVBoxLayout(tips_frame)
        tips_layout.setSpacing(16)
        
        tips_title = QLabel("💡 Financial Tips")
        tips_title.setStyleSheet(Styles.get_subtitle())
        tips_layout.addWidget(tips_title)
        
        self.tips_text = QTextEdit()
        self.tips_text.setReadOnly(True)
        self.tips_text.setMinimumHeight(180)
        self.tips_text.setStyleSheet("""
            QTextEdit {
                border: none;
                background: transparent;
                font-size: 14px;
                color: #495057;
                line-height: 1.6;
            }
        """)
        tips_layout.addWidget(self.tips_text)
        
        main_layout.addWidget(tips_frame)
        
                           
        expense_frame = QFrame()
        expense_frame.setStyleSheet(Styles.get_card_style())
        expense_layout = QVBoxLayout(expense_frame)
        expense_layout.setSpacing(16)
        
        expense_title = QLabel("📈 Monthly Expense Breakdown")
        expense_title.setStyleSheet(Styles.get_subtitle())
        expense_layout.addWidget(expense_title)
        
        self.expense_breakdown = QTextEdit()
        self.expense_breakdown.setReadOnly(True)
        self.expense_breakdown.setMinimumHeight(240)
        self.expense_breakdown.setStyleSheet("""
            QTextEdit {
                border: none;
                background: transparent;
                font-size: 14px;
                color: #495057;
                line-height: 1.8;
                font-family: 'Consolas', 'Monaco', monospace;
            }
        """)
        expense_layout.addWidget(self.expense_breakdown)
        
        main_layout.addWidget(expense_frame)
        
                                                                     
        two_column_layout = QHBoxLayout()
        two_column_layout.setSpacing(24)
        
                         
        summary_frame = QFrame()
        summary_frame.setStyleSheet(Styles.get_card_style())
        summary_layout = QVBoxLayout(summary_frame)
        summary_layout.setSpacing(16)
        
        summary_title = QLabel("📅 Monthly Summary")
        summary_title.setStyleSheet(Styles.get_subtitle())
        summary_layout.addWidget(summary_title)
        
        self.monthly_summary = QTextEdit()
        self.monthly_summary.setReadOnly(True)
        self.monthly_summary.setMinimumHeight(200)
        self.monthly_summary.setStyleSheet("""
            QTextEdit {
                border: none;
                background: transparent;
                font-size: 13px;
                color: #495057;
                line-height: 1.5;
            }
        """)
        summary_layout.addWidget(self.monthly_summary)
        
        two_column_layout.addWidget(summary_frame, 1)
        
                           
        donation_frame = QFrame()
        donation_frame.setStyleSheet(Styles.get_card_style())
        donation_layout = QVBoxLayout(donation_frame)
        donation_layout.setSpacing(16)
        
        donation_title = QLabel("❤️ Donation Impact")
        donation_title.setStyleSheet(Styles.get_subtitle())
        donation_layout.addWidget(donation_title)
        
        self.donation_insights = QTextEdit()
        self.donation_insights.setReadOnly(True)
        self.donation_insights.setMinimumHeight(200)
        self.donation_insights.setStyleSheet("""
            QTextEdit {
                border: none;
                background: transparent;
                font-size: 14px;
                color: #495057;
                line-height: 1.6;
                text-align: center;
            }
        """)
        donation_layout.addWidget(self.donation_insights)
        
        two_column_layout.addWidget(donation_frame, 1)
        
        main_layout.addLayout(two_column_layout)
        
                                           
        main_layout.addStretch()
        
        scroll_area.setWidget(container)
        
                                        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_area)
        
    def load_insights(self):
        """Load and display financial insights"""
                   
        tips = self.get_financial_tips()
        self.tips_text.setHtml(f"<div style='color: #2c3e50;'>{tips}</div>")
        
                                
        expenses = self.get_expense_breakdown()
        self.expense_breakdown.setHtml(f"<div style='color: #2c3e50;'>{expenses}</div>")
        
                              
        summary = self.get_monthly_summary()
        self.monthly_summary.setHtml(f"<div style='color: #2c3e50;'>{summary}</div>")
        
                                
        donations = self.get_donation_insights()
        self.donation_insights.setHtml(f"<div style='color: #2c3e50;'>{donations}</div>")
        
    def get_financial_tips(self):
        """Generate financial tips based on user data"""
        stats = self.db.get_summary_stats()
        balance = self.db.get_current_balance()
        monthly_income = self.db.get_monthly_income()
        tips = []

        total_income = float(stats.get('total_income', 0) or 0)
        total_expenses = float(stats.get('total_expenses', 0) or 0)
        total_donations = float(stats.get('total_donations', 0) or 0)
        total_outflow = total_expenses + total_donations
        monthly_leftover = monthly_income - total_outflow if monthly_income > 0 else 0.0

        if total_income <= 0:
            tips.append("🌟 <b>Start by adding income first.</b> Personalized guidance appears once income exists.")
            return "<br><br>".join(tips)

        savings_rate = ((total_income - total_outflow) / total_income) * 100
        if savings_rate < 0:
            tips.append(
                f"⚠️ <b>Cashflow alert:</b> You are overspending by <b>${abs(total_income - total_outflow):,.2f}</b>. "
                "Reduce variable expenses first (eating out, shopping, subscriptions)."
            )
        elif savings_rate < 10:
            tips.append(
                f"📉 <b>Low savings buffer:</b> Current savings rate is <b>{savings_rate:.1f}%</b>. "
                "Try increasing it to at least 10%."
            )
        elif savings_rate < 20:
            tips.append(f"📊 <b>Good pace:</b> You are saving <b>{savings_rate:.1f}%</b> of income.")
        else:
            tips.append(f"🎉 <b>Strong discipline:</b> You are saving <b>{savings_rate:.1f}%</b> of income.")

        if monthly_income > 0:
            recommended = self.service.savings_guidance(monthly_income, AppConstants.SAVINGS_GUIDE_RATE)
            monthly_gap = recommended - monthly_leftover
            if monthly_gap > 0:
                tips.append(
                    f"💡 <b>Personalized target:</b> Recommended monthly savings is <b>${recommended:,.2f}</b>. "
                    f"You are short by <b>${monthly_gap:,.2f}/month</b> based on current monthly totals."
                )
            else:
                tips.append(
                    f"✅ <b>On target:</b> Recommended monthly savings is <b>${recommended:,.2f}</b>, "
                    f"and you are currently above it by <b>${abs(monthly_gap):,.2f}/month</b>."
                )
            budget_summary = self.db.get_budget_summary()
            if budget_summary.get('total_categories', 0) > 0:
                total_budget = float(budget_summary.get('total_budget', 0) or 0)
                budget_usage = float(budget_summary.get('budget_usage_percentage', 0) or 0)
                budget_to_income_ratio = (total_budget / monthly_income * 100) if monthly_income > 0 else 0
                if budget_to_income_ratio > 100:
                    tips.append(
                        f"🚫 <b>Budget too high:</b> Your total budget is <b>{budget_to_income_ratio:.1f}%</b> of monthly income. "
                        "Lower budget limits so total budgets stay within income."
                    )
                elif budget_to_income_ratio > 90:
                    tips.append(
                        f"⚠️ <b>Tight budget setup:</b> Total budgets use <b>{budget_to_income_ratio:.1f}%</b> of income. "
                        "Leave more room for savings and emergencies."
                    )

                if budget_usage > 100:
                    tips.append(
                        f"🔥 <b>Spending too much:</b> You are at <b>{budget_usage:.1f}%</b> of your planned budgets this month. "
                        "Cut non-essentials now to avoid further overspending."
                    )
                elif budget_usage > 85:
                    tips.append(
                        f"⚠️ <b>High budget usage:</b> You have used <b>{budget_usage:.1f}%</b> of monthly budgets."
                    )

            active_goals = self.db.get_goals()
            pending_goals = [
                g for g in active_goals
                if float(g.get('target_amount', 0) or 0) > float(g.get('current_amount', 0) or 0)
            ]
            if pending_goals:
                next_goal = min(
                    pending_goals,
                    key=lambda g: g.get('deadline_date') or "9999-12-31"
                )
                remaining_amount = max(
                    0.0, float(next_goal.get('target_amount', 0) or 0) - float(next_goal.get('current_amount', 0) or 0)
                )
                months_left = 0
                try:
                    deadline_date = datetime.strptime(next_goal['deadline_date'], "%Y-%m-%d").date()
                    today = date.today()
                    months_left = max(1, (deadline_date.year - today.year) * 12 + (deadline_date.month - today.month))
                except Exception:
                    months_left = 12

                needed_per_month = remaining_amount / months_left if months_left > 0 else remaining_amount
                if monthly_leftover < needed_per_month:
                    tips.append(
                        f"🎯 <b>Goal requires higher saving:</b> To reach <b>{next_goal['name']}</b>, "
                        f"you need about <b>${needed_per_month:,.2f}/month</b> for the next {months_left} month(s), "
                        f"but current leftover is <b>${monthly_leftover:,.2f}/month</b>."
                    )
                else:
                    tips.append(
                        f"✅ <b>Goal on track:</b> At current pace, you can fund <b>{next_goal['name']}</b> by deadline "
                        f"with about <b>${needed_per_month:,.2f}/month</b>."
                    )

        if total_donations > 0:
            donation_percentage = (total_donations / total_income) * 100
            tips.append(
                f"❤️ <b>Giving impact:</b> Donations are <b>{donation_percentage:.1f}%</b> of your income. "
                "Keep donations sustainable so goals and essentials stay funded."
            )

        categories, totals, _ = self.db.get_transactions_by_category('month')
        if categories and totals:
            top_idx = max(range(len(totals)), key=lambda i: totals[i])
            top_category = categories[top_idx]
            top_amount = totals[top_idx]
            tips.append(
                f"🧭 <b>Biggest spend category:</b> <b>{top_category}</b> at <b>${top_amount:,.2f}</b> this month. "
                f"Cutting this by 10% frees about <b>${top_amount * 0.10:,.2f}</b>."
            )

        if balance < 0:
            tips.append(
                f"🚨 <b>Negative balance:</b> Current balance is <b>${balance:,.2f}</b>. "
                "Pause non-essential spending until balance turns positive."
            )
        else:
            tips.append(f"💼 <b>Current balance:</b> <b>${balance:,.2f}</b>. Keep at least one month of expenses as buffer.")

        tips.append("📅 <b>Weekly review:</b> Compare spending vs budget once per week and adjust fast.")
        return "<br><br>".join(tips)
    
    def get_expense_breakdown(self):
        """Generate expense breakdown by category"""
        categories, totals, colors = self.db.get_transactions_by_category('month')
        
        if not categories:
            return "<div style='text-align: center; color: #95a5a6; font-style: italic; padding: 40px;'>No expenses recorded this month.</div>"
        
        html = ""
        total_expenses = sum(totals)
        
        for i, (category, amount) in enumerate(zip(categories, totals)):
            percentage = (amount / total_expenses) * 100 if total_expenses > 0 else 0
            
                                                      
            bar_width = min(int(percentage / AppConstants.EXPENSE_BREAKDOWN_BAR_DIVISOR), AppConstants.EXPENSE_BREAKDOWN_BAR_MAX)
            bar = "█" * bar_width
            
            html += f"""
            <div style='margin-bottom: 16px;'>
                <div style='display: flex; justify-content: space-between; margin-bottom: 4px;'>
                    <span style='font-weight: 600; color: {colors[i] if i < len(colors) else '#3498db'}'>
                        {category}
                    </span>
                    <span style='color: #6c757d;'>
                        ${amount:,.2f} ({percentage:.1f}%)
                    </span>
                </div>
                <div style='color: {colors[i] if i < len(colors) else '#3498db'}; font-family: monospace; font-size: 12px;'>
                    {bar}
                </div>
            </div>
            """
        
                   
        html += f"""
        <div style='margin-top: 24px; padding-top: 16px; border-top: 2px solid #dee2e6;'>
            <div style='display: flex; justify-content: space-between; font-weight: bold; font-size: 15px;'>
                <span>Total Expenses:</span>
                <span style='color: {Styles.DANGER_COLOR};'>${total_expenses:,.2f}</span>
            </div>
        </div>
        """
        
        return html
    
    def get_monthly_summary(self):
        """Generate monthly summary"""
        months, incomes, expenses, donations = self.db.get_monthly_summary()
        
        if not months:
            return "<div style='text-align: center; color: #95a5a6; font-style: italic; padding: 40px;'>No monthly data available yet.</div>"
        
        html = "<table width='100%' style='border-collapse: collapse;'>"
        html += "<tr style='background-color: #f8f9fa; border-bottom: 2px solid #dee2e6;'>"
        html += "<th style='padding: 10px; text-align: left; font-size: 12px; color: #6c757d;'>Month</th>"
        html += "<th style='padding: 10px; text-align: right; font-size: 12px; color: #6c757d;'>Income</th>"
        html += "<th style='padding: 10px; text-align: right; font-size: 12px; color: #6c757d;'>Expenses</th>"
        html += "<th style='padding: 10px; text-align: right; font-size: 12px; color: #6c757d;'>Donations</th>"
        html += "<th style='padding: 10px; text-align: right; font-size: 12px; color: #6c757d;'>Net</th>"
        html += "</tr>"
        
        for i in range(len(months)):
            month_display = datetime.strptime(months[i], "%Y-%m").strftime("%b %Y")
            
                           
            net = incomes[i] - expenses[i] - donations[i]
            net_color = Styles.SUCCESS_COLOR if net >= 0 else Styles.DANGER_COLOR
            net_sign = "+" if net >= 0 else ""
            
            html += f"""
            <tr style='border-bottom: 1px solid #e9ecef;'>
                <td style='padding: 10px; font-size: 13px;'>{month_display}</td>
                <td style='padding: 10px; text-align: right; font-size: 13px; color: {Styles.SUCCESS_COLOR};'>${incomes[i]:,.2f}</td>
                <td style='padding: 10px; text-align: right; font-size: 13px; color: {Styles.DANGER_COLOR};'>${expenses[i]:,.2f}</td>
                <td style='padding: 10px; text-align: right; font-size: 13px; color: #e67e22;'>${donations[i]:,.2f}</td>
                <td style='padding: 10px; text-align: right; font-size: 13px; font-weight: 600; color: {net_color};'>{net_sign}${abs(net):,.2f}</td>
            </tr>
            """
        
        html += "</table>"
        
                                     
        if len(months) > 0:
            latest_net = incomes[-1] - expenses[-1] - donations[-1]
            net_text = "surplus" if latest_net >= 0 else "deficit"
            net_color = Styles.SUCCESS_COLOR if latest_net >= 0 else Styles.DANGER_COLOR
            net_sign = "+" if latest_net >= 0 else ""
            
            html += f"""
            <div style='margin-top: 20px; padding: 16px; background-color: #f8f9fa; border-radius: 8px; text-align: center;'>
                <div style='font-weight: 600; color: {net_color}; font-size: 14px;'>
                    Last month: {net_sign}${abs(latest_net):,.2f} {net_text}
                </div>
            </div>
            """
        
        return html
    
    def get_donation_insights(self):
        """Generate donation insights"""
        stats = self.db.get_summary_stats()
        
        if stats['total_donations'] == 0:
            return """
            <div style='padding: 40px 20px; text-align: center;'>
                <div style='font-size: 48px; color: #e67e22; margin-bottom: 16px;'>❤️</div>
                <div style='color: #6c757d; font-size: 15px; line-height: 1.6;'>
                    No donations yet.<br>
                    Even small donations can make a big difference!<br><br>
                    <span style='color: #e67e22; font-weight: 600;'>Tip:</span> Start with a small, sustainable donation goal.
                </div>
            </div>
            """
        
        html = f"""
        <div style='padding: 20px; text-align: center;'>
            <div style='font-size: 48px; color: #e67e22; margin-bottom: 16px;'>❤️</div>
            <div style='font-weight: bold; font-size: 20px; color: #e67e22; margin-bottom: 24px;'>
                Total Donated: ${stats['total_donations']:,.2f}
            </div>
        """
        
                                             
        if stats['total_donations'] >= 1000:
            html += """
            <div style='margin-bottom: 16px; padding: 12px; background-color: #fff8e1; border-radius: 8px;'>
                <div style='font-size: 16px; color: #e67e22; font-weight: 600; margin-bottom: 4px;'>🌍 Major Impact</div>
                <div style='color: #6c757d; font-size: 13px;'>
                    Your donations could provide meals for hundreds of people!
                </div>
            </div>
            """
        elif stats['total_donations'] >= 100:
            html += """
            <div style='margin-bottom: 16px; padding: 12px; background-color: #fff8e1; border-radius: 8px;'>
                <div style='font-size: 16px; color: #e67e22; font-weight: 600; margin-bottom: 4px;'>🤝 Community Builder</div>
                <div style='color: #6c757d; font-size: 13px;'>
                    You're supporting meaningful change in your community!
                </div>
            </div>
            """
        else:
            html += """
            <div style='margin-bottom: 16px; padding: 12px; background-color: #fff8e1; border-radius: 8px;'>
                <div style='font-size: 16px; color: #e67e22; font-weight: 600; margin-bottom: 4px;'>🌟 Every Bit Helps</div>
                <div style='color: #6c757d; font-size: 13px;'>
                    Small donations add up to create big impact!
                </div>
            </div>
            """
        
                                  
        months, _, _, donations = self.db.get_monthly_summary()
        if len(months) > 0 and sum(donations) > 0:
            avg_monthly = sum(donations) / len(months)
            html += f"""
            <div style='margin-bottom: 12px;'>
                <div style='font-weight: 600; color: #2c3e50; font-size: 14px;'>📅 Monthly Average:</div>
                <div style='color: #e67e22; font-size: 16px; font-weight: bold;'>${avg_monthly:,.2f}</div>
            </div>
            """
            
                                  
            non_zero_months = sum(1 for d in donations if d > 0)
            consistency = (non_zero_months / len(months)) * 100
            consistency_color = Styles.SUCCESS_COLOR if consistency >= 50 else Styles.WARNING_COLOR
            
            html += f"""
            <div style='margin-top: 16px; padding: 12px; background-color: #f8f9fa; border-radius: 8px;'>
                <div style='font-weight: 600; color: #2c3e50; font-size: 14px; margin-bottom: 4px;'>📊 Donation Consistency</div>
                <div style='color: {consistency_color}; font-size: 18px; font-weight: bold;'>{consistency:.0f}%</div>
                <div style='color: #6c757d; font-size: 12px;'>
                    {non_zero_months} out of {len(months)} months included donations
                </div>
            </div>
            """
        
        html += "</div>"
        return html

class BudgetsView(QWidget):
    """View for managing budgets"""
    
    budget_updated = pyqtSignal()
    
    def __init__(self, db, service=None):
        super().__init__()
        self.db = db
        self.service = service or FinanceService(db)
        self.setup_ui()
        self.load_budgets()
        
    def setup_ui(self):
                                                
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("border: none; background: transparent;")
        
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(28)
        main_layout.setContentsMargins(32, 24, 32, 40)
        
                
        header_layout = QHBoxLayout()
        
        title = QLabel("💳 Expenses & Budgets")
        title.setStyleSheet(Styles.get_section_title())
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        set_income_button = QPushButton("💵 Set Monthly Income")
        set_income_button.setStyleSheet(Styles.get_secondary_button())
        set_income_button.clicked.connect(self.show_income_dialog)
        header_layout.addWidget(set_income_button)

        refresh_button = QPushButton("🔄 Refresh")
        refresh_button.setStyleSheet(Styles.get_secondary_button())
        refresh_button.clicked.connect(self.refresh_view)
        header_layout.addWidget(refresh_button)
        
        main_layout.addLayout(header_layout)
        
                                
        income_frame = QFrame()
        income_frame.setStyleSheet(Styles.get_card_style())
        income_layout = QVBoxLayout(income_frame)
        income_layout.setSpacing(12)
        
        self.income_label = QLabel("Monthly Income: Not Set")
        self.income_label.setStyleSheet("font-weight: 600; color: #2c3e50; font-size: 16px;")
        
        income_tip = QLabel("💡 Set your monthly income to help create realistic budgets")
        income_tip.setStyleSheet("color: #6c757d; font-size: 13px;")
        
        income_layout.addWidget(self.income_label)
        income_layout.addWidget(income_tip)
        
        main_layout.addWidget(income_frame)

                           
        create_frame = QFrame()
        create_frame.setStyleSheet(Styles.get_card_style())
        create_layout = QVBoxLayout(create_frame)
        create_layout.setSpacing(16)
        
        create_title = QLabel("Create New Budget")
        create_title.setStyleSheet(Styles.get_subtitle())
        create_layout.addWidget(create_title)
        
                            
        category_layout = QVBoxLayout()
        category_layout.setSpacing(8)
        category_layout.addWidget(QLabel("Category:"))
        
        self.category_combo = QComboBox()
        self.category_combo.setStyleSheet(Styles.get_input_style())
        
                                      
        categories = self.db.get_categories('expense')
        for cat in categories:
            self.category_combo.addItem(f"{cat['icon']} {cat['name']}", cat['id'])
        
        category_layout.addWidget(self.category_combo)
        create_layout.addLayout(category_layout)
        
                       
        amount_layout = QVBoxLayout()
        amount_layout.setSpacing(8)
        amount_layout.addWidget(QLabel("Monthly Budget:"))
        
        self.amount_input = QDoubleSpinBox()
        self.amount_input.setPrefix("$ ")
        self.amount_input.setRange(AppConstants.MIN_AMOUNT, AppConstants.MAX_BUDGET_AMOUNT)
        self.amount_input.setValue(AppConstants.DEFAULT_BUDGET_AMOUNT)
        self.amount_input.setStyleSheet(Styles.get_input_style())
        amount_layout.addWidget(self.amount_input)
        create_layout.addLayout(amount_layout)

        self.budget_tip_label = QLabel("")
        self.budget_tip_label.setStyleSheet(
            "color: #6c757d; font-size: 13px; padding: 8px; background-color: #f8f9fa; border-radius: 6px;"
        )
        self.budget_tip_label.setWordWrap(True)
        create_layout.addWidget(self.budget_tip_label)
        
                       
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        create_button = QPushButton("➕ Add Budget")
        create_button.clicked.connect(self.add_budget)
        create_button.setStyleSheet(Styles.get_success_button())
        create_button.setMinimumWidth(150)
        button_layout.addWidget(create_button)
        button_layout.addStretch()
        
        create_layout.addLayout(button_layout)
        
        main_layout.addWidget(create_frame)
        
                       
        table_frame = QFrame()
        table_frame.setStyleSheet(Styles.get_card_style())
        table_layout = QVBoxLayout(table_frame)
        table_layout.setSpacing(16)
        table_layout.setContentsMargins(16, 12, 16, 16)
        
        table_title = QLabel("Your Budgets")
        table_title.setStyleSheet(Styles.get_subtitle())
        table_layout.addWidget(table_title)
        
                      
        self.budgets_table = QTableWidget()
        self.budgets_table.setColumnCount(6)
        self.budgets_table.setHorizontalHeaderLabels([
            "Category", "Monthly Budget", "Spent", "Remaining", "Progress", "Actions"
        ])
        self.budgets_table.setStyleSheet(Styles.get_table_style())
        self.budgets_table.setWordWrap(True)
        header = self.budgets_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setVisible(True)
        header.setFixedHeight(40)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setMinimumSectionSize(90)
        self.budgets_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.budgets_table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.budgets_table.verticalHeader().setVisible(False)
        self.budgets_table.setCornerButtonEnabled(False)
        self.budgets_table.setShowGrid(True)
        self.budgets_table.setMinimumHeight(420)
        self.budgets_table.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        
        table_layout.addWidget(self.budgets_table)
        
        table_frame.setMinimumHeight(500)
        table_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout.addWidget(table_frame)
        self._resize_budget_columns()

        self.category_combo.currentIndexChanged.connect(self.update_budget_tip)
        self.amount_input.valueChanged.connect(self.update_budget_tip)
        
                                           
        main_layout.addStretch()
        
        scroll_area.setWidget(container)
        
                    
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_area)
        
                               
        self.update_income_display()
        self.update_budget_tip()

    def refresh_view(self):
        """Refresh visible data in this tab."""
        self.update_income_display()
        self.load_budgets()
        
    def update_income_display(self):
        """Update the monthly income display"""
        monthly_income = self.db.get_monthly_income()
        if monthly_income > 0:
            self.income_label.setText(f"Monthly Income: ${monthly_income:,.2f}")
        else:
            self.income_label.setText("Monthly Income: Not Set")
        self.update_budget_tip()

    def update_budget_tip(self):
        """Show budget recommendation for selected category."""
        if not hasattr(self, "category_combo") or not hasattr(self, "amount_input"):
            return

        monthly_income = self.db.get_monthly_income()
        category_text = self.category_combo.currentText()
        category_name = self.service._extract_category_name(category_text)
        guide = self.service.category_budget_guidance(monthly_income, category_name)

        if not guide.get('ok'):
            self.budget_tip_label.setText(guide['message'])
            return

        current_value = self.amount_input.value()
        if current_value < guide['min_target']:
            position_text = "below the suggested range"
            color = Styles.WARNING_COLOR
        elif current_value > guide['max_target']:
            position_text = "above the suggested range"
            color = Styles.DANGER_COLOR
        else:
            position_text = "within the suggested range"
            color = Styles.SUCCESS_COLOR

        self.budget_tip_label.setStyleSheet(
            f"color: {color}; font-size: 13px; padding: 8px; background-color: #f8f9fa; border-radius: 6px;"
        )
        self.budget_tip_label.setText(
            f"Suggested {category_name} budget: ${guide['recommended']:,.2f} "
            f"({guide['ratio']*100:.0f}% of income). "
            f"Recommended range: ${guide['min_target']:,.2f} - ${guide['max_target']:,.2f}. "
            f"Current amount is {position_text}."
        )

    def update_savings_guide(self):
        """Update savings guide text"""
        monthly_income = self.db.get_monthly_income()
        if monthly_income <= 0:
            self.savings_guide_label.setText(
                "Set your monthly income to get a recommended savings target."
            )
            return
        
        recommended = self.service.savings_guidance(monthly_income, AppConstants.SAVINGS_GUIDE_RATE)
        self.savings_guide_label.setText(
            f"A common goal is to save about {AppConstants.SAVINGS_GUIDE_RATE*100:.0f}% of income. "
            f"That’s roughly ${recommended:,.2f} per month for you."
        )
    def update_savings_calculator(self):
        """Update savings calculator results"""
        amount = self.calc_amount.value()
        periods = self.calc_period.value()
        is_years = self.calc_unit.currentText() == "Years"
        annual_rate = self.calc_rate.value() / 100
        target_amount = self.calc_target.value()
        monthly_save = self.calc_monthly_save.value()

        total_no_growth = self.service.savings_projection(amount, 0, periods, is_years=is_years)
        total_with_growth = self.service.savings_projection(amount, annual_rate, periods, is_years=is_years)
        mode = self.calc_mode.currentIndex()

        if mode == 0:
            label_period = "years" if is_years else "months"
            if annual_rate > 0:
                self.calc_result.setText(
                    f"If you save ${amount:.2f} for {periods} {label_period}, "
                    f"you would have about ${total_no_growth:.2f} without growth, "
                    f"or ${total_with_growth:.2f} at {self.calc_rate.value():.2f}% annual growth."
                )
            else:
                self.calc_result.setText(
                    f"If you save ${amount:.2f} for {periods} {label_period}, "
                    f"you would have about ${total_no_growth:.2f}."
                )
            return

        months_needed = self.service.months_to_reach_target(target_amount, monthly_save, annual_rate)
        if mode == 1:
            if months_needed is None:
                self.calc_result.setText(
                    f"Target planner: cannot reach ${target_amount:.2f} with ${monthly_save:.2f}/month "
                    f"within the configured horizon."
                )
                return

            years = months_needed // 12
            months = months_needed % 12
            if years > 0 and months > 0:
                duration_text = f"{years} years and {months} months"
            elif years > 0:
                duration_text = f"{years} years"
            else:
                duration_text = f"{months} months"

            self.calc_result.setText(
                f"To reach ${target_amount:.2f} while saving ${monthly_save:.2f}/month, "
                f"estimated time is {duration_text} at {self.calc_rate.value():.2f}% annual growth."
            )
            return

        required_monthly = self.service.required_monthly_saving(
            target_amount, periods, annual_rate, is_years=is_years
        )
        label_period = "years" if is_years else "months"
        self.calc_result.setText(
            f"To reach ${target_amount:.2f} in {periods} {label_period}, "
            f"you need to save about ${required_monthly:.2f} per month "
            f"at {self.calc_rate.value():.2f}% annual growth."
        )

    def update_calculator_mode(self):
        """Show only inputs relevant to the selected calculator mode."""
        mode = self.calc_mode.currentIndex()
        save_mode = mode == 0
        target_time_mode = mode == 1
        required_save_mode = mode == 2

        self.calc_save_amount_label.setVisible(save_mode)
        self.calc_amount.setVisible(save_mode)
        self.calc_period_label.setVisible(save_mode or required_save_mode)
        self.calc_period.setVisible(save_mode or required_save_mode)
        self.calc_period_unit_label.setVisible(save_mode or required_save_mode)
        self.calc_unit.setVisible(save_mode or required_save_mode)

        self.calc_target_label.setVisible(target_time_mode or required_save_mode)
        self.calc_target.setVisible(target_time_mode or required_save_mode)
        self.calc_monthly_save_label.setVisible(target_time_mode)
        self.calc_monthly_save.setVisible(target_time_mode)

        self.update_savings_calculator()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_budget_columns()

    def _resize_budget_columns(self):
        """Keep the table width fixed; fit text within columns."""
        if not hasattr(self, "budgets_table"):
            return
        viewport_width = self.budgets_table.viewport().width()
        if viewport_width <= 0:
            return
                                                                                    
        ratios = [0.22, 0.16, 0.12, 0.14, 0.22, 0.14]
        total = sum(ratios)
        widths = [int(viewport_width * (r / total)) for r in ratios]
                                                         
        remainder = viewport_width - sum(widths)
        widths[-1] += remainder
        min_size = self.budgets_table.horizontalHeader().minimumSectionSize()
        for i, w in enumerate(widths):
            self.budgets_table.setColumnWidth(i, max(w, min_size))
    
    def show_income_dialog(self):
        """Show dialog to set monthly income"""
        dialog = IncomeSettingDialog(self.db, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_income = dialog.get_income()
            if self.db.set_monthly_income(new_income):
                self.update_income_display()
                show_toast(self, f"Monthly income set to ${new_income:,.2f}", level="success")
            else:
                QMessageBox.critical(self, "Error", "Failed to update monthly income.")
    
    def load_budgets(self):
        """Load and display budgets"""
        budgets = self.db.get_budgets()
        
                     
        self.budgets_table.setRowCount(0)
        
        if not budgets:
                                   
            self.budgets_table.setRowCount(1)
            placeholder = QTableWidgetItem("No budgets set. Create your first budget above!")
            placeholder.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setForeground(QColor(Styles.GRAY_COLOR))
            self.budgets_table.setItem(0, 0, placeholder)
            self.budgets_table.setSpan(0, 0, 1, 6)                           
            return
        
        self.budgets_table.setRowCount(len(budgets))
        
        for i, budget in enumerate(budgets):
            self.budgets_table.setRowHeight(i, 62)
                      
            category_item = QTableWidgetItem(f"{budget['icon']} {budget['category_name']}")
            category_item.setData(Qt.ItemDataRole.UserRole, budget['id'])
            category_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            
                            
            budget_item = QTableWidgetItem(f"${budget['monthly_limit']:,.2f}")
            budget_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
                   
            spent_item = QTableWidgetItem(f"${budget['current_spent']:,.2f}")
            spent_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if budget['exceeded']:
                spent_item.setForeground(QColor(Styles.DANGER_COLOR))
            
                       
            remaining_item = QTableWidgetItem(f"${budget['remaining']:,.2f}")
            remaining_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if budget['remaining'] < 0:
                remaining_item.setForeground(QColor(Styles.DANGER_COLOR))
            elif budget['remaining'] < budget['monthly_limit'] * AppConstants.BUDGET_REMAINING_WARNING_RATIO:
                remaining_item.setForeground(QColor(Styles.WARNING_COLOR))
            else:
                remaining_item.setForeground(QColor(Styles.SUCCESS_COLOR))
            
                                      
            progress_widget = QWidget()
            progress_layout = QHBoxLayout(progress_widget)
            progress_layout.setContentsMargins(6, 0, 6, 0)
            progress_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            progress_bar = QProgressBar()
            progress_bar.setRange(0, int(AppConstants.PROGRESS_MAX))
            progress_bar.setValue(int(budget['percentage_clamped']))
            progress_bar.setMinimumHeight(34)
            progress_bar.setTextVisible(True)
            progress_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            progress_bar.setFormat(f"{budget['percentage']:.1f}%")
            
                                           
            if budget['percentage'] >= AppConstants.BUDGET_OVER_THRESHOLD:
                progress_bar.setStyleSheet(f"""
                    QProgressBar {{
                        border: 1px solid {Styles.BORDER_COLOR};
                        border-radius: 3px;
                        text-align: center;
                        height: 28px;
                        font-size: 12px;
                        background-color: #f8f9fa;
                    }}
                    QProgressBar::chunk {{
                        background-color: {Styles.DANGER_COLOR};
                        border-radius: 2px;
                    }}
                """)
            elif budget['percentage'] >= AppConstants.BUDGET_WARNING_THRESHOLD:
                progress_bar.setStyleSheet(f"""
                    QProgressBar {{
                        border: 1px solid {Styles.BORDER_COLOR};
                        border-radius: 3px;
                        text-align: center;
                        height: 28px;
                        font-size: 12px;
                        background-color: #f8f9fa;
                    }}
                    QProgressBar::chunk {{
                        background-color: {Styles.WARNING_COLOR};
                        border-radius: 2px;
                    }}
                """)
            else:
                progress_bar.setStyleSheet(f"""
                    QProgressBar {{
                        border: 1px solid {Styles.BORDER_COLOR};
                        border-radius: 3px;
                        text-align: center;
                        height: 28px;
                        font-size: 12px;
                        background-color: #f8f9fa;
                    }}
                    QProgressBar::chunk {{
                        background-color: {Styles.SUCCESS_COLOR};
                        border-radius: 2px;
                    }}
                """)
            
            progress_layout.addWidget(progress_bar, alignment=Qt.AlignmentFlag.AlignCenter)
            
                     
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(6, 0, 6, 0)
            actions_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            delete_button = QPushButton("Delete")
            delete_button.setToolTip("Delete budget")
            delete_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: 1px solid {Styles.DANGER_COLOR};
                    border-radius: 4px;
                    padding: 8px 10px;
                    color: {Styles.DANGER_COLOR};
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: #ffeaea;
                }}
            """)
            delete_button.setMinimumHeight(34)
            delete_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            delete_button.clicked.connect(lambda checked, b=budget: self.delete_budget(b))
            
            actions_layout.addWidget(delete_button, alignment=Qt.AlignmentFlag.AlignCenter)
            
                                
            self.budgets_table.setItem(i, 0, category_item)
            self.budgets_table.setItem(i, 1, budget_item)
            self.budgets_table.setItem(i, 2, spent_item)
            self.budgets_table.setItem(i, 3, remaining_item)
            self.budgets_table.setCellWidget(i, 4, progress_widget)
            self.budgets_table.setCellWidget(i, 5, actions_widget)
        
        self._resize_budget_columns()
    
    def add_budget(self):
        """Add a new budget"""
        category_id = self.category_combo.currentData()
        amount = self.amount_input.value()
        
        if category_id is None:
            QMessageBox.warning(self, "Error", "Please select a category.")
            return
        
        if amount <= 0:
            QMessageBox.warning(self, "Error", "Please enter a positive amount.")
            return

        monthly_income = self.db.get_monthly_income()
        if monthly_income <= 0:
            QMessageBox.warning(
                self,
                "Set Monthly Income",
                "Please set your monthly income before creating budgets."
            )
            return
        
                                                          
        existing_budget = self.db.get_category_budget(category_id)
        if existing_budget is not None:
            reply = QMessageBox.question(
                self, "Budget Exists",
                f"A budget already exists for this category (${existing_budget:,.2f}).\n"
                "Do you want to update it",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return

                                                 
        current_total = sum(b['monthly_limit'] for b in self.db.get_budgets())
        if existing_budget is not None:
            current_total -= existing_budget
        new_total = current_total + amount
        if new_total > monthly_income:
            QMessageBox.warning(
                self,
                "Budget Limit Exceeded",
                f"Total budgets cannot exceed monthly income.\n\n"
                f"Monthly Income: ${monthly_income:,.2f}\n"
                f"Current Total Budgets: ${current_total:,.2f}\n"
                f"Proposed Total Budgets: ${new_total:,.2f}"
            )
            return
        
        success = self.db.set_budget(category_id, amount)
        
        if success:
            show_toast(self, "Budget created successfully! 💰", level="success")
            self.clear_form()
            self.load_budgets()
            self.budget_updated.emit()
        else:
            QMessageBox.critical(self, "Error", "Failed to create budget.")
    
    def delete_budget(self, budget):
        """Delete a budget"""
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete the budget for {budget['category_name']}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            success = self.db.delete_budget(budget['id'])
            
            if success:
                show_toast(self, "Budget deleted successfully!", level="success")
                self.load_budgets()
                self.budget_updated.emit()
            else:
                QMessageBox.critical(self, "Error", "Failed to delete budget.")
    
    def clear_form(self):
        """Clear the form inputs"""
        self.amount_input.setValue(AppConstants.DEFAULT_BUDGET_AMOUNT)

                                                           
class FinePrintView(QWidget):
    """View for legal and policy fine print."""

    SOURCE_URL = "https://github.com/CtrlAltSpace/Finance-Manager"

    PRIVACY_POLICY_TEXT = """**1. Data Collection**
The application does not collect personal data beyond the information voluntarily entered by users for financial tracking purposes.
Financial information entered by users may constitute personal data depending on local laws; such data remains stored locally and is never transmitted to the developer.

**2. Local Data Storage**
All financial records, transaction data, and settings are stored locally on the user's device. The developers do not receive, transmit, or store user financial data on external servers.

**3. No Data Sharing**
The application does not sell, rent, disclose, or share any user data with third parties, advertisers, government entities, or external organizations, except where required by applicable law.

**4. No Remote Access**
The developers have no remote access to user data stored within the application.

**5. Data Security**
Reasonable technical safeguards are implemented to protect data stored within the application; however, no system can guarantee absolute security. Users are responsible for securing their own devices.

**6. User Responsibility**
Users are solely responsible for backing up their data and maintaining device security.

**7. Children's Privacy**
The application is not directed toward children and does not knowingly collect or transmit personal information. Any data entered by users remains stored locally on their device.

**8. Policy Updates**
This Privacy Policy may be updated periodically. Continued use of the application constitutes acceptance of any revisions.

**9. Legal Compliance**
This policy is intended to comply with applicable international data protection laws, including general principles found in regulations such as GDPR, CCPA, and similar frameworks.

**10. Contact**
Questions regarding this policy should be directed to the application developer via official support channels."""

    DISCLAIMER_TEXT = """This program is free software licensed under the GNU Affero General Public License, Version 3 (AGPLv3), or any later version.

This program is distributed in the hope that it will be useful, but **WITHOUT ANY WARRANTY**, to the fullest extent permitted by applicable law. The program is provided “AS IS” without warranty of any kind, whether express or implied, including, but not limited to, the implied warranties of merchantability, fitness for a particular purpose, accuracy, reliability, or non-infringement.

The entire risk as to the quality, performance, correctness of financial calculations, data integrity, and suitability for any purpose rests with the user. This software is intended solely for personal financial organization and informational purposes and does not constitute financial, investment, legal, tax, or professional advice.

To the maximum extent permitted by applicable law, **no copyright holder, contributor, developer, distributor, or any party who modifies or conveys this program** shall be liable for any damages arising from the use of or inability to use the program, including but not limited to:

• Financial loss or incorrect financial decisions
• Loss, corruption, or inaccuracy of data
• Loss of profits or business interruption
• System failures, security breaches, or unauthorized access
• Any indirect, incidental, special, consequential, or punitive damages

This limitation applies even if such parties have been advised of the possibility of such damages.

Nothing in this disclaimer is intended to limit liability where such limitation is prohibited by applicable law. Where local law does not permit full exclusion of liability, liability shall be limited to the maximum extent permitted.

By using, modifying, or distributing this program, you acknowledge and accept the terms of this disclaimer in conjunction with the GNU Affero General Public License.
You should have received a copy of the GNU Affero General Public License along with this program. If not, see <https://www.gnu.org/licenses/>"""

    AGPL_TEXT = """                    GNU AFFERO GENERAL PUBLIC LICENSE
                       Version 3, 19 November 2007

 Copyright (C) 2007 Free Software Foundation, Inc. <https://fsf.org/>
 Everyone is permitted to copy and distribute verbatim copies
 of this license document, but changing it is not allowed.

                            Preamble

  The GNU Affero General Public License is a free, copyleft license for
software and other kinds of works, specifically designed to ensure
cooperation with the community in the case of network server software.

  The licenses for most software and other practical works are designed
to take away your freedom to share and change the works.  By contrast,
our General Public Licenses are intended to guarantee your freedom to
share and change all versions of a program--to make sure it remains free
software for all its users.

  When we speak of free software, we are referring to freedom, not
price.  Our General Public Licenses are designed to make sure that you
have the freedom to distribute copies of free software (and charge for
them if you wish), that you receive source code or can get it if you
want it, that you can change the software or use pieces of it in new
free programs, and that you know you can do these things.

  Developers that use our General Public Licenses protect your rights
with two steps: (1) assert copyright on the software, and (2) offer
you this License which gives you legal permission to copy, distribute
and/or modify the software.

  A secondary benefit of defending all users' freedom is that
improvements made in alternate versions of the program, if they
receive widespread use, become available for other developers to
incorporate.  Many developers of free software are heartened and
encouraged by the resulting cooperation.  However, in the case of
software used on network servers, this result may fail to come about.
The GNU General Public License permits making a modified version and
letting the public access it on a server without ever releasing its
source code to the public.

  The GNU Affero General Public License is designed specifically to
ensure that, in such cases, the modified source code becomes available
to the community.  It requires the operator of a network server to
provide the source code of the modified version running there to the
users of that server.  Therefore, public use of a modified version, on
a publicly accessible server, gives the public access to the source
code of the modified version.

  An older license, called the Affero General Public License and
published by Affero, was designed to accomplish similar goals.  This is
a different license, not a version of the Affero GPL, but Affero has
released a new version of the Affero GPL which permits relicensing under
this license.

  The precise terms and conditions for copying, distribution and
modification follow.

                       TERMS AND CONDITIONS

  0. Definitions.

  "This License" refers to version 3 of the GNU Affero General Public License.

  "Copyright" also means copyright-like laws that apply to other kinds of
works, such as semiconductor masks.

  "The Program" refers to any copyrightable work licensed under this
License.  Each licensee is addressed as "you".  "Licensees" and
"recipients" may be individuals or organizations.

  To "modify" a work means to copy from or adapt all or part of the work
in a fashion requiring copyright permission, other than the making of an
exact copy.  The resulting work is called a "modified version" of the
earlier work or a work "based on" the earlier work.

  A "covered work" means either the unmodified Program or a work based
on the Program.

  To "propagate" a work means to do anything with it that, without
permission, would make you directly or secondarily liable for
infringement under applicable copyright law, except executing it on a
computer or modifying a private copy.  Propagation includes copying,
distribution (with or without modification), making available to the
public, and in some countries other activities as well.

  To "convey" a work means any kind of propagation that enables other
parties to make or receive copies.  Mere interaction with a user through
a computer network, with no transfer of a copy, is not conveying.

  An interactive user interface displays "Appropriate Legal Notices"
to the extent that it includes a convenient and prominently visible
feature that (1) displays an appropriate copyright notice, and (2)
tells the user that there is no warranty for the work (except to the
extent that warranties are provided), that licensees may convey the
work under this License, and how to view a copy of this License.  If
the interface presents a list of user commands or options, such as a
menu, a prominent item in the list meets this criterion.

  1. Source Code.

  The "source code" for a work means the preferred form of the work
for making modifications to it.  "Object code" means any non-source
form of a work.

  A "Standard Interface" means an interface that either is an official
standard defined by a recognized standards body, or, in the case of
interfaces specified for a particular programming language, one that
is widely used among developers working in that language.

  The "System Libraries" of an executable work include anything, other
than the work as a whole, that (a) is included in the normal form of
packaging a Major Component, but which is not part of that Major
Component, and (b) serves only to enable use of the work with that
Major Component, or to implement a Standard Interface for which an
implementation is available to the public in source code form.  A
"Major Component", in this context, means a major essential component
(kernel, window system, and so on) of the specific operating system
(if any) on which the executable work runs, or a compiler used to
produce the work, or an object code interpreter used to run it.

  The "Corresponding Source" for a work in object code form means all
the source code needed to generate, install, and (for an executable
work) run the object code and to modify the work, including scripts to
control those activities.  However, it does not include the work's
System Libraries, or general-purpose tools or generally available free
programs which are used unmodified in performing those activities but
which are not part of the work.  For example, Corresponding Source
includes interface definition files associated with source files for
the work, and the source code for shared libraries and dynamically
linked subprograms that the work is specifically designed to require,
such as by intimate data communication or control flow between those
subprograms and other parts of the work.

  The Corresponding Source need not include anything that users
can regenerate automatically from other parts of the Corresponding
Source.

  The Corresponding Source for a work in source code form is that
same work.

  2. Basic Permissions.

  All rights granted under this License are granted for the term of
copyright on the Program, and are irrevocable provided the stated
conditions are met.  This License explicitly affirms your unlimited
permission to run the unmodified Program.  The output from running a
covered work is covered by this License only if the output, given its
content, constitutes a covered work.  This License acknowledges your
rights of fair use or other equivalent, as provided by copyright law.

  You may make, run and propagate covered works that you do not
convey, without conditions so long as your license otherwise remains
in force.  You may convey covered works to others for the sole purpose
of having them make modifications exclusively for you, or provide you
with facilities for running those works, provided that you comply with
the terms of this License in conveying all material for which you do
not control copyright.  Those thus making or running the covered works
for you must do so exclusively on your behalf, under your direction
and control, on terms that prohibit them from making any copies of
your copyrighted material outside their relationship with you.

  Conveying under any other circumstances is permitted solely under
the conditions stated below.  Sublicensing is not allowed; section 10
makes it unnecessary.

  3. Protecting Users' Legal Rights From Anti-Circumvention Law.

  No covered work shall be deemed part of an effective technological
measure under any applicable law fulfilling obligations under article
11 of the WIPO copyright treaty adopted on 20 December 1996, or
similar laws prohibiting or restricting circumvention of such
measures.

  When you convey a covered work, you waive any legal power to forbid
circumvention of technological measures to the extent such circumvention
is effected by exercising rights under this License with respect to
the covered work, and you disclaim any intention to limit operation or
modification of the work as a means of enforcing, against the work's
users, your or third parties' legal rights to forbid circumvention of
technological measures.

  4. Conveying Verbatim Copies.

  You may convey verbatim copies of the Program's source code as you
receive it, in any medium, provided that you conspicuously and
appropriately publish on each copy an appropriate copyright notice;
keep intact all notices stating that this License and any
non-permissive terms added in accord with section 7 apply to the code;
keep intact all notices of the absence of any warranty; and give all
recipients a copy of this License along with the Program.

  You may charge any price or no price for each copy that you convey,
and you may offer support or warranty protection for a fee.

  5. Conveying Modified Source Versions.

  You may convey a work based on the Program, or the modifications to
produce it from the Program, in the form of source code under the
terms of section 4, provided that you also meet all of these conditions:

    a) The work must carry prominent notices stating that you modified
    it, and giving a relevant date.

    b) The work must carry prominent notices stating that it is
    released under this License and any conditions added under section
    7.  This requirement modifies the requirement in section 4 to
    "keep intact all notices".

    c) You must license the entire work, as a whole, under this
    License to anyone who comes into possession of a copy.  This
    License will therefore apply, along with any applicable section 7
    additional terms, to the whole of the work, and all its parts,
    regardless of how they are packaged.  This License gives no
    permission to license the work in any other way, but it does not
    invalidate such permission if you have separately received it.

    d) If the work has interactive user interfaces, each must display
    Appropriate Legal Notices; however, if the Program has interactive
    interfaces that do not display Appropriate Legal Notices, your
    work need not make them do so.

  A compilation of a covered work with other separate and independent
works, which are not by their nature extensions of the covered work,
and which are not combined with it such as to form a larger program,
in or on a volume of a storage or distribution medium, is called an
"aggregate" if the compilation and its resulting copyright are not
used to limit the access or legal rights of the compilation's users
beyond what the individual works permit.  Inclusion of a covered work
in an aggregate does not cause this License to apply to the other
parts of the aggregate.

  6. Conveying Non-Source Forms.

  You may convey a covered work in object code form under the terms
of sections 4 and 5, provided that you also convey the
machine-readable Corresponding Source under the terms of this License,
in one of these ways:

    a) Convey the object code in, or embodied in, a physical product
    (including a physical distribution medium), accompanied by the
    Corresponding Source fixed on a durable physical medium
    customarily used for software interchange.

    b) Convey the object code in, or embodied in, a physical product
    (including a physical distribution medium), accompanied by a
    written offer, valid for at least three years and valid for as
    long as you offer spare parts or customer support for that product
    model, to give anyone who possesses the object code either (1) a
    copy of the Corresponding Source for all the software in the
    product that is covered by this License, on a durable physical
    medium customarily used for software interchange, for a price no
    more than your reasonable cost of physically performing this
    conveying of source, or (2) access to copy the
    Corresponding Source from a network server at no charge.

    c) Convey individual copies of the object code with a copy of the
    written offer to provide the Corresponding Source.  This
    alternative is allowed only occasionally and noncommercially, and
    only if you received the object code with such an offer, in accord
    with subsection 6b.

    d) Convey the object code by offering access from a designated
    place (gratis or for a charge), and offer equivalent access to the
    Corresponding Source in the same way through the same place at no
    further charge.  You need not require recipients to copy the
    Corresponding Source along with the object code.  If the place to
    copy the object code is a network server, the Corresponding Source
    may be on a different server (operated by you or a third party)
    that supports equivalent copying facilities, provided you maintain
    clear directions next to the object code saying where to find the
    Corresponding Source.  Regardless of what server hosts the
    Corresponding Source, you remain obligated to ensure that it is
    available for as long as needed to satisfy these requirements.

    e) Convey the object code using peer-to-peer transmission, provided
    you inform other peers where the object code and Corresponding
    Source of the work are being offered to the general public at no
    charge under subsection 6d.

  A separable portion of the object code, whose source code is excluded
from the Corresponding Source as a System Library, need not be
included in conveying the object code work.

  A "User Product" is either (1) a "consumer product", which means any
tangible personal property which is normally used for personal, family,
or household purposes, or (2) anything designed or sold for incorporation
into a dwelling.  In determining whether a product is a consumer product,
doubtful cases shall be resolved in favor of coverage.  For a particular
product received by a particular user, "normally used" refers to a
typical or common use of that class of product, regardless of the status
of the particular user or of the way in which the particular user
actually uses, or expects or is expected to use, the product.  A product
is a consumer product regardless of whether the product has substantial
commercial, industrial or non-consumer uses, unless such uses represent
the only significant mode of use of the product.

  "Installation Information" for a User Product means any methods,
procedures, authorization keys, or other information required to install
and execute modified versions of a covered work in that User Product from
a modified version of its Corresponding Source.  The information must
suffice to ensure that the continued functioning of the modified object
code is in no case prevented or interfered with solely because
modification has been made.

  If you convey an object code work under this section in, or with, or
specifically for use in, a User Product, and the conveying occurs as
part of a transaction in which the right of possession and use of the
User Product is transferred to the recipient in perpetuity or for a
fixed term (regardless of how the transaction is characterized), the
Corresponding Source conveyed under this section must be accompanied
by the Installation Information.  But this requirement does not apply
if neither you nor any third party retains the ability to install
modified object code on the User Product (for example, the work has
been installed in ROM).

  The requirement to provide Installation Information does not include a
requirement to continue to provide support service, warranty, or updates
for a work that has been modified or installed by the recipient, or for
the User Product in which it has been modified or installed.  Access to a
network may be denied when the modification itself materially and
adversely affects the operation of the network or violates the rules and
protocols for communication across the network.

  Corresponding Source conveyed, and Installation Information provided,
in accord with this section must be in a format that is publicly
documented (and with an implementation available to the public in
source code form), and must require no special password or key for
unpacking, reading or copying.

  7. Additional Terms.

  "Additional permissions" are terms that supplement the terms of this
License by making exceptions from one or more of its conditions.
Additional permissions that are applicable to the entire Program shall
be treated as though they were included in this License, to the extent
that they are valid under applicable law.  If additional permissions
apply only to part of the Program, that part may be used separately
under those permissions, but the entire Program remains governed by
this License without regard to the additional permissions.

  When you convey a copy of a covered work, you may at your option
remove any additional permissions from that copy, or from any part of
it.  (Additional permissions may be written to require their own
removal in certain cases when you modify the work.)  You may place
additional permissions on material, added by you to a covered work,
for which you have or can give appropriate copyright permission.

  Notwithstanding any other provision of this License, for material you
add to a covered work, you may (if authorized by the copyright holders of
that material) supplement the terms of this License with terms:

    a) Disclaiming warranty or limiting liability differently from the
    terms of sections 15 and 16 of this License; or

    b) Requiring preservation of specified reasonable legal notices or
    author attributions in that material or in the Appropriate Legal
    Notices displayed by works containing it; or

    c) Prohibiting misrepresentation of the origin of that material, or
    requiring that modified versions of such material be marked in
    reasonable ways as different from the original version; or

    d) Limiting the use for publicity purposes of names of licensors or
    authors of the material; or

    e) Declining to grant rights under trademark law for use of some
    trade names, trademarks, or service marks; or

    f) Requiring indemnification of licensors and authors of that
    material by anyone who conveys the material (or modified versions of
    it) with contractual assumptions of liability to the recipient, for
    any liability that these contractual assumptions directly impose on
    those licensors and authors.

  All other non-permissive additional terms are considered "further
restrictions" within the meaning of section 10.  If the Program as you
received it, or any part of it, contains a notice stating that it is
governed by this License along with a term that is a further
restriction, you may remove that term.  If a license document contains
a further restriction but permits relicensing or conveying under this
License, you may add to a covered work material governed by the terms
of that license document, provided that the further restriction does
not survive such relicensing or conveying.

  If you add terms to a covered work in accord with this section, you
must place, in the relevant source files, a statement of the
additional terms that apply to those files, or a notice indicating
where to find the applicable terms.

  Additional terms, permissive or non-permissive, may be stated in the
form of a separately written license, or stated as exceptions;
the above requirements apply either way.

  8. Termination.

  You may not propagate or modify a covered work except as expressly
provided under this License.  Any attempt otherwise to propagate or
modify it is void, and will automatically terminate your rights under
this License (including any patent licenses granted under the third
paragraph of section 11).

  However, if you cease all violation of this License, then your
license from a particular copyright holder is reinstated (a)
provisionally, unless and until the copyright holder explicitly and
finally terminates your license, and (b) permanently, if the copyright
holder fails to notify you of the violation by some reasonable means
prior to 60 days after the cessation.

  Moreover, your license from a particular copyright holder is
reinstated permanently if the copyright holder notifies you of the
violation by some reasonable means, this is the first time you have
received notice of violation of this License (for any work) from that
copyright holder, and you cure the violation prior to 30 days after
your receipt of the notice.

  Termination of your rights under this section does not terminate the
licenses of parties who have received copies or rights from you under
this License.  If your rights have been terminated and not permanently
reinstated, you do not qualify to receive new licenses for the same
material under section 10.

  9. Acceptance Not Required for Having Copies.

  You are not required to accept this License in order to receive or
run a copy of the Program.  Ancillary propagation of a covered work
occurring solely as a consequence of using peer-to-peer transmission
to receive a copy likewise does not require acceptance.  However,
nothing other than this License grants you permission to propagate or
modify any covered work.  These actions infringe copyright if you do
not accept this License.  Therefore, by modifying or propagating a
covered work, you indicate your acceptance of this License to do so.

  10. Automatic Licensing of Downstream Recipients.

  Each time you convey a covered work, the recipient automatically
receives a license from the original licensors, to run, modify and
propagate that work, subject to this License.  You are not responsible
for enforcing compliance by third parties with this License.

  An "entity transaction" is a transaction transferring control of an
organization, or substantially all assets of one, or subdividing an
organization, or merging organizations.  If propagation of a covered
work results from an entity transaction, each party to that
transaction who receives a copy of the work also receives whatever
licenses to the work the party's predecessor in interest had or could
give under the previous paragraph, plus a right to possession of the
Corresponding Source of the work from the predecessor in interest, if
the predecessor has it or can get it with reasonable efforts.

  You may not impose any further restrictions on the exercise of the
rights granted or affirmed under this License.  For example, you may
not impose a license fee, royalty, or other charge for exercise of
rights granted under this License, and you may not initiate litigation
(including a cross-claim or counterclaim in a lawsuit) alleging that
any patent claim is infringed by making, using, selling, offering for
sale, or importing the Program or any portion of it.

  11. Patents.

  A "contributor" is a copyright holder who authorizes use under this
License of the Program or a work on which the Program is based.  The
work thus licensed is called the contributor's "contributor version".

  A contributor's "essential patent claims" are all patent claims
owned or controlled by the contributor, whether already acquired or
hereafter acquired, that would be infringed by some manner, permitted
by this License, of making, using, or selling its contributor version,
but do not include claims that would be infringed only as a
consequence of further modification of the contributor version.  For
purposes of this definition, "control" includes the right to grant
patent sublicenses in a manner consistent with the requirements of
this License.

  Each contributor grants you a non-exclusive, worldwide, royalty-free
patent license under the contributor's essential patent claims, to
make, use, sell, offer for sale, import and otherwise run, modify and
propagate the contents of its contributor version.

  In the following three paragraphs, a "patent license" is any express
agreement or commitment, however denominated, not to enforce a patent
(such as an express permission to practice a patent or covenant not to
sue for patent infringement).  To "grant" such a patent license to a
party means to make such an agreement or commitment not to enforce a
patent against the party.

  If you convey a covered work, knowingly relying on a patent license,
and the Corresponding Source of the work is not available for anyone
to copy, free of charge and under the terms of this License, through a
publicly available network server or other readily accessible means,
then you must either (1) cause the Corresponding Source to be so
available, or (2) arrange to deprive yourself of the benefit of the
patent license for this particular work, or (3) arrange, in a manner
consistent with the requirements of this License, to extend the patent
license to downstream recipients.  "Knowingly relying" means you have
actual knowledge that, but for the patent license, your conveying the
covered work in a country, or your recipient's use of the covered work
in a country, would infringe one or more identifiable patents in that
country that you have reason to believe are valid.

  If, pursuant to or in connection with a single transaction or
arrangement, you convey, or propagate by procuring conveyance of, a
covered work, and grant a patent license to some of the parties
receiving the covered work authorizing them to use, propagate, modify
or convey a specific copy of the covered work, then the patent license
you grant is automatically extended to all recipients of the covered
work and works based on it.

  A patent license is "discriminatory" if it does not include within
the scope of its coverage, prohibits the exercise of, or is
conditioned on the non-exercise of one or more of the rights that are
specifically granted under this License.  You may not convey a covered
work if you are a party to an arrangement with a third party that is
in the business of distributing software, under which you make payment
to the third party based on the extent of your activity of conveying
the work, and under which the third party grants, to any of the
parties who would receive the covered work from you, a discriminatory
patent license (a) in connection with copies of the covered work
conveyed by you (or copies made from those copies), or (b) primarily
for and in connection with specific products or compilations that
contain the covered work, unless you entered into that arrangement,
or that patent license was granted, prior to 28 March 2007.

  Nothing in this License shall be construed as excluding or limiting
any implied license or other defenses to infringement that may
otherwise be available to you under applicable patent law.

  12. No Surrender of Others' Freedom.

  If conditions are imposed on you (whether by court order, agreement or
otherwise) that contradict the conditions of this License, they do not
excuse you from the conditions of this License.  If you cannot convey a
covered work so as to satisfy simultaneously your obligations under this
License and any other pertinent obligations, then as a consequence you may
not convey it at all.  For example, if you agree to terms that obligate you
to collect a royalty for further conveying from those to whom you convey
the Program, the only way you could satisfy both those terms and this
License would be to refrain entirely from conveying the Program.

  13. Remote Network Interaction; Use with the GNU General Public License.

  Notwithstanding any other provision of this License, if you modify the
Program, your modified version must prominently offer all users
interacting with it remotely through a computer network (if your version
supports such interaction) an opportunity to receive the Corresponding
Source of your version by providing access to the Corresponding Source
from a network server at no charge, through some standard or customary
means of facilitating copying of software.  This Corresponding Source
shall include the Corresponding Source for any work covered by version 3
of the GNU General Public License that is incorporated pursuant to the
following paragraph.

  Notwithstanding any other provision of this License, you have
permission to link or combine any covered work with a work licensed
under version 3 of the GNU General Public License into a single
combined work, and to convey the resulting work.  The terms of this
License will continue to apply to the part which is the covered work,
but the work with which it is combined will remain governed by version
3 of the GNU General Public License.

  14. Revised Versions of this License.

  The Free Software Foundation may publish revised and/or new versions of
the GNU Affero General Public License from time to time.  Such new versions
will be similar in spirit to the present version, but may differ in detail to
address new problems or concerns.

  Each version is given a distinguishing version number.  If the
Program specifies that a certain numbered version of the GNU Affero General
Public License "or any later version" applies to it, you have the
option of following the terms and conditions either of that numbered
version or of any later version published by the Free Software
Foundation.  If the Program does not specify a version number of the
GNU Affero General Public License, you may choose any version ever published
by the Free Software Foundation.

  If the Program specifies that a proxy can decide which future
versions of the GNU Affero General Public License can be used, that proxy's
public statement of acceptance of a version permanently authorizes you
to choose that version for the Program.

  Later license versions may give you additional or different
permissions.  However, no additional obligations are imposed on any
author or copyright holder as a result of your choosing to follow a
later version.

  15. Disclaimer of Warranty.

  THERE IS NO WARRANTY FOR THE PROGRAM, TO THE EXTENT PERMITTED BY
APPLICABLE LAW.  EXCEPT WHEN OTHERWISE STATED IN WRITING THE COPYRIGHT
HOLDERS AND/OR OTHER PARTIES PROVIDE THE PROGRAM "AS IS" WITHOUT WARRANTY
OF ANY KIND, EITHER EXPRESSED OR IMPLIED, INCLUDING, BUT NOT LIMITED TO,
THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
PURPOSE.  THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE OF THE PROGRAM
IS WITH YOU.  SHOULD THE PROGRAM PROVE DEFECTIVE, YOU ASSUME THE COST OF
ALL NECESSARY SERVICING, REPAIR OR CORRECTION.

  16. Limitation of Liability.

  IN NO EVENT UNLESS REQUIRED BY APPLICABLE LAW OR AGREED TO IN WRITING
WILL ANY COPYRIGHT HOLDER, OR ANY OTHER PARTY WHO MODIFIES AND/OR CONVEYS
THE PROGRAM AS PERMITTED ABOVE, BE LIABLE TO YOU FOR DAMAGES, INCLUDING ANY
GENERAL, SPECIAL, INCIDENTAL OR CONSEQUENTIAL DAMAGES ARISING OUT OF THE
USE OR INABILITY TO USE THE PROGRAM (INCLUDING BUT NOT LIMITED TO LOSS OF
DATA OR DATA BEING RENDERED INACCURATE OR LOSSES SUSTAINED BY YOU OR THIRD
PARTIES OR A FAILURE OF THE PROGRAM TO OPERATE WITH ANY OTHER PROGRAMS),
EVEN IF SUCH HOLDER OR OTHER PARTY HAS BEEN ADVISED OF THE POSSIBILITY OF
SUCH DAMAGES.

  17. Interpretation of Sections 15 and 16.

  If the disclaimer of warranty and limitation of liability provided
above cannot be given local legal effect according to their terms,
reviewing courts shall apply local law that most closely approximates
an absolute waiver of all civil liability in connection with the
Program, unless a warranty or assumption of liability accompanies a
copy of the Program in return for a fee.

                     END OF TERMS AND CONDITIONS

            How to Apply These Terms to Your New Programs

  If you develop a new program, and you want it to be of the greatest
possible use to the public, the best way to achieve this is to make it
free software which everyone can redistribute and change under these terms.

  To do so, attach the following notices to the program.  It is safest
to attach them to the start of each source file to most effectively
state the exclusion of warranty; and each file should have at least
the "copyright" line and a pointer to where the full notice is found.

    <one line to give the program's name and a brief idea of what it does.>
    Copyright (C) <year>  <name of author>

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published
    by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.

Also add information on how to contact you by electronic and paper mail.

  If your software can interact with users remotely through a computer
network, you should also make sure that it provides a way for users to
get its source.  For example, if your program is a web application, its
interface could display a "Source" link that leads users to an archive
of the code.  There are many ways you could offer source, and different
solutions will be better for different programs; see section 13 for the
specific requirements.

  You should also get your employer (if you work as a programmer) or school,
if any, to sign a "copyright disclaimer" for the program, if necessary.
For more information on this, and how to apply and follow the GNU AGPL, see
<https://www.gnu.org/licenses/>.
"""

    CREDITS_TEXT = """The name "WarpVar" is used with permission from its owner.

All rights to the name belong to WarpVar.
No official affiliation or endorsement is implied.


Scripture quotations are from the NIV®.

New International Version (NIV)
Holy Bible, New International Version®, NIV® Copyright
©1973, 1978, 1984, 2011 by Biblica, Inc.® Used by permission.
All rights reserved worldwide."""

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("border: none; background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(20)
        layout.setContentsMargins(32, 24, 32, 32)

        title = QLabel("Fine Print")
        title.setStyleSheet(Styles.get_section_title())
        layout.addWidget(title)

        layout.addWidget(self._create_rich_section("Privacy Policy", self.PRIVACY_POLICY_TEXT))
        layout.addWidget(self._create_rich_section("Disclaimer of Liability and Warranty (AGPLv3-Compliant Notice)", self.DISCLAIMER_TEXT))
        layout.addWidget(self._create_plain_section("Open Source License (AGPLv3)", self.AGPL_TEXT))
        layout.addWidget(self._create_plain_section("Credits", self.CREDITS_TEXT))
        layout.addWidget(self._create_source_section())
        layout.addStretch()

        scroll_area.setWidget(container)
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(scroll_area)

    def _create_rich_section(self, heading, content):
        frame = QFrame()
        frame.setStyleSheet(Styles.get_card_style())
        section_layout = QVBoxLayout(frame)
        section_layout.setSpacing(10)

        header = QLabel(heading)
        header.setStyleSheet(Styles.get_subtitle())
        section_layout.addWidget(header)

        text = AutoHeightTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet(Styles.get_input_style())
        text.setHtml(self._bold_markup_to_html(content))
        text.refresh_height()
        section_layout.addWidget(text)
        return frame

    def _create_plain_section(self, heading, content):
        frame = QFrame()
        frame.setStyleSheet(Styles.get_card_style())
        section_layout = QVBoxLayout(frame)
        section_layout.setSpacing(10)

        header = QLabel(heading)
        header.setStyleSheet(Styles.get_subtitle())
        section_layout.addWidget(header)

        text = AutoHeightTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet(Styles.get_input_style() + "QTextEdit { font-family: Consolas, 'Courier New', monospace; }")
        text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        text.setPlainText(content)
        text.refresh_height()
        section_layout.addWidget(text)
        return frame

    def _create_source_section(self):
        frame = QFrame()
        frame.setStyleSheet(Styles.get_card_style())
        section_layout = QVBoxLayout(frame)
        section_layout.setSpacing(10)

        header = QLabel("Source Code")
        header.setStyleSheet(Styles.get_subtitle())
        section_layout.addWidget(header)

        source_button = QPushButton("View Source Code")
        source_button.setStyleSheet(Styles.get_secondary_button())
        source_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        source_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.SOURCE_URL)))
        section_layout.addWidget(source_button)
        return frame

    def _bold_markup_to_html(self, text):
        escaped = html.escape(text)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped, flags=re.DOTALL)
        escaped = escaped.replace("\n", "<br>")
        return f"<div style='font-size:14px; color:#2c3e50; line-height:1.5;'>{escaped}</div>"

                                                       
class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.db.process_recurring_items()
        self.service = FinanceService(self.db)
        self.setup_ui()
                                         
        self.notification_manager = NotificationManager(self.db, self)
        
    def setup_ui(self):
        self.setWindowTitle("Finance Manager")
        self.setMinimumSize(1200, 800)
        
                                 
        self.setStyleSheet(Styles.get_app_style())
        
                               
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
                                     
        nav_bar = self.create_navigation_bar()
        main_layout.addWidget(nav_bar)
        
                                         
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget, 1)
        
                              
        self.dashboard_view = DashboardView(self.db)
        self.income_view = IncomeView(self.db, self.service)
        self.expense_view = ExpenseView(self.db, self.service)
        self.donation_view = DonationView(self.db, self.service)
        self.goals_view = GoalsView(self.db)
        self.insights_view = InsightsView(self.db)
        self.budgets_view = BudgetsView(self.db, self.service)
        self.fine_print_view = FinePrintView()
        
        self.stacked_widget.addWidget(self.dashboard_view)
        self.stacked_widget.addWidget(self.income_view)
        self.stacked_widget.addWidget(self.expense_view)
        self.stacked_widget.addWidget(self.donation_view)
        self.stacked_widget.addWidget(self.goals_view)
        self.stacked_widget.addWidget(self.insights_view)
        self.stacked_widget.addWidget(self.budgets_view)
        self.stacked_widget.addWidget(self.fine_print_view)
        
                         
        self.connect_signals()

                                   
        self.show_dashboard()
        
    def create_navigation_bar(self):
        """Create the left navigation bar."""
        nav_widget = QWidget()
        nav_widget.setStyleSheet(f"""
            QWidget {{
                background-color: white;
            }}
        """)
        nav_widget.setFixedWidth(250)

        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(12, 12, 12, 12)
        nav_layout.setSpacing(10)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)

        icon_label = QLabel("💙")
        icon_label.setStyleSheet("font-size: 20px;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_label = QLabel("Finance Manager")
        title_label.setStyleSheet("font-size: 18px; font-weight: 600; color: #2c3e50;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle_label = QLabel("Control • Awareness • Kindness")
        subtitle_label.setStyleSheet("color: #95a5a6; font-size: 10px; margin-top: 2px;")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_layout.addWidget(icon_label)
        title_layout.addWidget(title_label)
        title_layout.addWidget(subtitle_label)

        nav_layout.addLayout(title_layout)

        nav_buttons = [
            ("🏠", "Dashboard", self.show_dashboard, "dashboard"),
            ("💰", "Income", self.show_income, "income"),
            ("💳", "Expenses and Budgets", self.show_budgets, "expense"),
            ("🎯", "Goals and Savings", self.show_goals, "goals"),
            ("❤️", "Donate", self.show_donation, "donate"),
            ("📈", "Insights", self.show_insights, "insights"),
            ("📝", "Fine Print", self.show_fine_print, "fineprint")
        ]

        for icon, text, callback, key in nav_buttons:
            btn = QPushButton(f"{icon} {text}")
            btn.clicked.connect(callback)
            btn.setMinimumHeight(40)
            btn.setStyleSheet(f"""
                QPushButton {{
                    padding: 8px 12px;
                    border-radius: 6px;
                    background-color: transparent;
                    color: #495057;
                    border: none;
                    font-size: 13px;
                    font-weight: 500;
                    text-align: left;
                }}
                QPushButton:hover {{
                    background-color: #f8f9fa;
                    color: {Styles.PRIMARY_COLOR};
                }}
                QPushButton:pressed {{
                    background-color: #e9ecef;
                }}
                QPushButton[active="true"] {{
                    background-color: {Styles.PRIMARY_COLOR};
                    color: white;
                    font-weight: 600;
                }}
            """)
            nav_layout.addWidget(btn)
            setattr(self, f"{key}_button", btn)

        nav_layout.addStretch()
        delete_all_button = QPushButton("🗑️ Delete All Saved Data")
        delete_all_button.setToolTip("Permanently delete all saved data and close the app")
        delete_all_button.setStyleSheet(Styles.get_danger_button())
        delete_all_button.clicked.connect(self.delete_all_saved_data)
        nav_layout.addWidget(delete_all_button)

        return nav_widget
        
    def connect_signals(self):
        """Connect signals between components"""
        self.income_view.transaction_added.connect(self.on_transaction_added)
        self.expense_view.transaction_added.connect(self.on_transaction_added)
        self.donation_view.transaction_added.connect(self.on_transaction_added)
        self.budgets_view.budget_updated.connect(self.on_budget_updated)
        self.dashboard_view.add_income_requested.connect(self.show_income)
        self.dashboard_view.add_expense_requested.connect(self.show_expense)
        self.dashboard_view.save_goal_requested.connect(self.show_goals)
        
    def on_transaction_added(self):
        """Handle when a transaction is added"""
        self.dashboard_view.refresh_data()
        self.insights_view.load_insights()
        self.budgets_view.load_budgets()
        
    def on_budget_updated(self):
        """Handle when a budget is updated"""
        self.dashboard_view.refresh_data()
        
    def show_dashboard(self):
        """Show dashboard view and update active button"""
        self.update_active_button("dashboard")
        self.stacked_widget.setCurrentWidget(self.dashboard_view)
        self.dashboard_view.refresh_data()
        
    def show_income(self):
        """Show income view and update active button"""
        self.update_active_button("income")
        self.stacked_widget.setCurrentWidget(self.income_view)
        self.income_view.update_balance()
        
    def show_expense(self):
        """Show expense view and update active button"""
        self.update_active_button("expense")
        self.stacked_widget.setCurrentWidget(self.expense_view)
        self.expense_view.update_balance()
        
    def show_donation(self):
        """Show donation view and update active button"""
        self.update_active_button("donate")
        self.stacked_widget.setCurrentWidget(self.donation_view)
        self.donation_view.update_balance()
        self.donation_view.load_goals()
        
    def show_goals(self):
        """Show goals view and update active button"""
        self.update_active_button("goals")
        self.stacked_widget.setCurrentWidget(self.goals_view)
        self.goals_view.load_goals()
        
    def show_budgets(self):
        """Show budgets view and update active button"""
        self.update_active_button("expense")
        self.stacked_widget.setCurrentWidget(self.budgets_view)
        self.budgets_view.load_budgets()
        
    def show_insights(self):
        """Show insights view and update active button"""
        self.update_active_button("insights")
        self.stacked_widget.setCurrentWidget(self.insights_view)
        self.insights_view.load_insights()

    def show_fine_print(self):
        """Show fine print view and update active button"""
        self.update_active_button("fineprint")
        self.stacked_widget.setCurrentWidget(self.fine_print_view)
    
    def update_active_button(self, active_view):
        """Update the active state of navigation buttons"""
                                  
        views = ["dashboard", "income", "expense", "donate", "goals", "insights", "fineprint"]
        
        for view in views:
            button = getattr(self, f"{view}_button", None)
            if button:
                                                      
                button.setProperty("active", "false")
                button.style().unpolish(button)
                button.style().polish(button)
        
                                           
        active_button = getattr(self, f"{active_view}_button", None)
        if active_button:
            active_button.setProperty("active", "true")
            active_button.style().unpolish(active_button)
            active_button.style().polish(active_button)

    def delete_all_saved_data(self):
        """Delete local database file after explicit confirmation and exit."""
        first_confirm = QMessageBox.warning(
            self,
            "Delete All Saved Data",
            "This will permanently delete all saved financial data and settings.\n\nDo you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if first_confirm != QMessageBox.StandardButton.Yes:
            return

        final_confirm = QMessageBox.warning(
            self,
            "Final Confirmation",
            "This action cannot be undone.\n\nDelete all saved data now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if final_confirm != QMessageBox.StandardButton.Yes:
            return

        db_path = self.db.db_path
        try:
            if hasattr(self, "notification_manager"):
                self.notification_manager.notification_timer.stop()

            paths_to_delete = [db_path, f"{db_path}-wal", f"{db_path}-shm"]
            for path in paths_to_delete:
                if os.path.exists(path):
                    os.remove(path)

            QMessageBox.information(
                self,
                "Data Deleted",
                "All saved data has been deleted.\nThe application will now close."
            )
            QApplication.instance().quit()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Delete Failed",
                f"Could not delete database file:\n{db_path}\n\n{e}"
            )

                                                                   
def main():
    """Main application entry point"""
    if os.name == "nt":
        try:
            myappid = "gabrian.financemanager.v1"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except (AttributeError, OSError):
            pass

    app = QApplication(sys.argv)
    app_icon = resolve_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
    
                           
    app.setStyle("Fusion")
    
                                               
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(Styles.LIGHT_COLOR))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(Styles.DARK_COLOR))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(Styles.LIGHT_COLOR))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(Styles.DARK_COLOR))
    palette.setColor(QPalette.ColorRole.Text, QColor(Styles.DARK_COLOR))
    palette.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(Styles.DARK_COLOR))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(Styles.PRIMARY_COLOR))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    class LicenseNoticeBox(QMessageBox):
        def __init__(self):
            super().__init__()
            self.closed_with_x = False

        def closeEvent(self, event):
            self.closed_with_x = True
            super().closeEvent(event)

    notice = LicenseNoticeBox()
    notice.setIcon(QMessageBox.Icon.Information)
    notice.setWindowTitle("License Notice")
    notice.setText(
        "This application is free software licensed under the GNU Affero General Public License Version 3 (AGPLv3).\n\n"
        "You are free to use, modify, and redistribute this software under the terms of the license.\n\n"
        "The complete source code is available at:\n"
        "https://github.com/CtrlAltSpace/Finance-Manager\n\n"
        "This program is provided WITHOUT ANY WARRANTY."
    )
    ok_button = notice.addButton(QMessageBox.StandardButton.Ok)
    notice.setDefaultButton(ok_button)
    notice.setEscapeButton(QMessageBox.StandardButton.NoButton)
    notice.exec()
    if notice.closed_with_x or notice.clickedButton() is not ok_button:
        sys.exit(0)

    warning = LicenseNoticeBox()
    warning.setIcon(QMessageBox.Icon.Warning)
    warning.setWindowTitle("Important Warning")
    warning.setText(
        "Do not follow everything the app suggests. This app can make mistakes.\n"
        "Always review the information and verify important decisions.\n\n"
        "By using this application, you acknowledge and agree to the Privacy Policy and Disclaimer of Liability."
    )
    warn_button = warning.addButton(QMessageBox.StandardButton.Ok)
    warning.setDefaultButton(warn_button)
    warning.setEscapeButton(QMessageBox.StandardButton.NoButton)
    warning.exec()
    if warning.closed_with_x or warning.clickedButton() is not warn_button:
        sys.exit(0)
    
                                                         
    window = MainWindow()
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)
    loading = LoadingScreen(total_duration_ms=1500)
    if not app_icon.isNull():
        loading.setWindowIcon(app_icon)

    def show_main_window():
        window.showMaximized()

    loading.loading_finished.connect(show_main_window)
    loading.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    # # Clean up old database file to start fresh (for development/testing purposes)
    # if os.path.exists("finance_data.db"):
    #     os.remove("finance_data.db")
    #     print("Old database removed. Starting fresh...")
    main()
