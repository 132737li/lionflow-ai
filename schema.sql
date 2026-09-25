-- =====================================================
-- LionFlow AI — Création de la base + utilisateur MySQL
-- À exécuter avec un compte root MySQL :
--   mysql -u root -p < schema.sql
-- =====================================================

CREATE DATABASE IF NOT EXISTS lionflow_ai
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'lionflow_user'@'localhost'
  IDENTIFIED BY 'password';

GRANT ALL PRIVILEGES ON lionflow_ai.* TO 'lionflow_user'@'localhost';
FLUSH PRIVILEGES;

USE lionflow_ai;

-- =====================================================
-- NOTE : Les tables ci-dessous sont créées automatiquement
-- par Flask-Migrate / Alembic via `flask db upgrade`.
-- Le DDL ci-dessous sert de référence et pour un import manuel.
-- =====================================================

-- ---------- users ----------
CREATE TABLE IF NOT EXISTS users (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    email           VARCHAR(255) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    first_name      VARCHAR(100),
    last_name       VARCHAR(100),
    role            ENUM('admin','user') NOT NULL DEFAULT 'user',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    is_verified     BOOLEAN NOT NULL DEFAULT FALSE,
    reset_token     VARCHAR(128),
    reset_token_exp DATETIME,
    last_login_at   DATETIME,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_users_email (email),
    INDEX idx_users_role (role)
) ENGINE=InnoDB;

-- ---------- businesses ----------
CREATE TABLE IF NOT EXISTS businesses (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    owner_id    INT NOT NULL,
    name        VARCHAR(200) NOT NULL,
    email       VARCHAR(255),
    phone       VARCHAR(30),
    address     VARCHAR(500),
    country     VARCHAR(100),
    logo_path   VARCHAR(500),
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_business_owner FOREIGN KEY (owner_id)
        REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_business_owner (owner_id),
    INDEX idx_business_name (name)
) ENGINE=InnoDB;

-- ---------- contacts ----------
CREATE TABLE IF NOT EXISTS contacts (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    business_id   INT NOT NULL,
    first_name    VARCHAR(120),
    last_name     VARCHAR(120),
    phone         VARCHAR(30) NOT NULL,
    email         VARCHAR(255),
    company       VARCHAR(200),
    tags          VARCHAR(500),
    status        ENUM('active','inactive','blocked') NOT NULL DEFAULT 'active',
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_contact_business FOREIGN KEY (business_id)
        REFERENCES businesses(id) ON DELETE CASCADE,
    UNIQUE KEY uq_contact_business_phone (business_id, phone),
    INDEX idx_contact_business (business_id),
    INDEX idx_contact_status (status)
) ENGINE=InnoDB;

-- ---------- whatsapp_accounts ----------
CREATE TABLE IF NOT EXISTS whatsapp_accounts (
    id                     INT AUTO_INCREMENT PRIMARY KEY,
    business_id            INT NOT NULL,
    name                   VARCHAR(150) NOT NULL,
    phone_number           VARCHAR(30) NOT NULL,
    phone_number_id        VARCHAR(80),
    business_account_id    VARCHAR(80),
    access_token_encrypted TEXT,
    status                 ENUM('disconnected','connected','error') NOT NULL DEFAULT 'disconnected',
    connected_at           DATETIME,
    created_at             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_waba_business FOREIGN KEY (business_id)
        REFERENCES businesses(id) ON DELETE CASCADE,
    INDEX idx_waba_business (business_id)
) ENGINE=InnoDB;

-- ---------- templates ----------
CREATE TABLE IF NOT EXISTS templates (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    business_id  INT NOT NULL,
    name         VARCHAR(150) NOT NULL,
    category     VARCHAR(80) DEFAULT 'general',
    content      TEXT NOT NULL,
    language     VARCHAR(10) DEFAULT 'fr',
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_template_business FOREIGN KEY (business_id)
        REFERENCES businesses(id) ON DELETE CASCADE,
    INDEX idx_template_business (business_id),
    INDEX idx_template_name (name)
) ENGINE=InnoDB;

-- ---------- campaigns ----------
CREATE TABLE IF NOT EXISTS campaigns (
    id                   INT AUTO_INCREMENT PRIMARY KEY,
    business_id          INT NOT NULL,
    template_id          INT,
    whatsapp_account_id  INT,
    name                 VARCHAR(200) NOT NULL,
    message              TEXT,
    status               ENUM('draft','scheduled','running','paused','completed','cancelled')
                         NOT NULL DEFAULT 'draft',
    scheduled_at         DATETIME,
    timezone             VARCHAR(64) DEFAULT 'UTC',
    started_at           DATETIME,
    finished_at          DATETIME,
    total_contacts       INT NOT NULL DEFAULT 0,
    sent_count           INT NOT NULL DEFAULT 0,
    delivered_count      INT NOT NULL DEFAULT 0,
    read_count           INT NOT NULL DEFAULT 0,
    failed_count         INT NOT NULL DEFAULT 0,
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_campaign_business FOREIGN KEY (business_id)
        REFERENCES businesses(id) ON DELETE CASCADE,
    CONSTRAINT fk_campaign_template FOREIGN KEY (template_id)
        REFERENCES templates(id) ON DELETE SET NULL,
    CONSTRAINT fk_campaign_waba FOREIGN KEY (whatsapp_account_id)
        REFERENCES whatsapp_accounts(id) ON DELETE SET NULL,
    INDEX idx_campaign_business (business_id),
    INDEX idx_campaign_status (status),
    INDEX idx_campaign_scheduled (scheduled_at)
) ENGINE=InnoDB;

-- ---------- messages ----------
CREATE TABLE IF NOT EXISTS messages (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    campaign_id       INT,
    contact_id        INT NOT NULL,
    whatsapp_account_id INT,
    content           TEXT,
    status            ENUM('pending','sent','delivered','read','failed')
                      NOT NULL DEFAULT 'pending',
    external_id       VARCHAR(120),
    error             VARCHAR(500),
    sent_at           DATETIME,
    delivered_at      DATETIME,
    read_at           DATETIME,
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_message_campaign FOREIGN KEY (campaign_id)
        REFERENCES campaigns(id) ON DELETE CASCADE,
    CONSTRAINT fk_message_contact FOREIGN KEY (contact_id)
        REFERENCES contacts(id) ON DELETE CASCADE,
    CONSTRAINT fk_message_waba FOREIGN KEY (whatsapp_account_id)
        REFERENCES whatsapp_accounts(id) ON DELETE SET NULL,
    INDEX idx_message_campaign (campaign_id),
    INDEX idx_message_contact (contact_id),
    INDEX idx_message_status (status),
    INDEX idx_message_external (external_id)
) ENGINE=InnoDB;

-- ---------- subscriptions ----------
CREATE TABLE IF NOT EXISTS subscriptions (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    business_id   INT NOT NULL,
    plan          ENUM('free','pro','business') NOT NULL DEFAULT 'free',
    status        ENUM('active','past_due','cancelled','expired') NOT NULL DEFAULT 'active',
    started_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at    DATETIME,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_sub_business FOREIGN KEY (business_id)
        REFERENCES businesses(id) ON DELETE CASCADE,
    INDEX idx_sub_business (business_id),
    INDEX idx_sub_status (status)
) ENGINE=InnoDB;

-- ---------- payments ----------
CREATE TABLE IF NOT EXISTS payments (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    business_id     INT NOT NULL,
    subscription_id INT,
    provider        VARCHAR(50) DEFAULT 'stripe',
    amount_cents    INT NOT NULL DEFAULT 0,
    currency        VARCHAR(10) DEFAULT 'EUR',
    status          ENUM('pending','succeeded','failed','refunded') NOT NULL DEFAULT 'pending',
    external_id     VARCHAR(120),
    payload         TEXT,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_payment_business FOREIGN KEY (business_id)
        REFERENCES businesses(id) ON DELETE CASCADE,
    CONSTRAINT fk_payment_sub FOREIGN KEY (subscription_id)
        REFERENCES subscriptions(id) ON DELETE SET NULL,
    INDEX idx_payment_business (business_id),
    INDEX idx_payment_status (status)
) ENGINE=InnoDB;

-- ---------- notifications ----------
CREATE TABLE IF NOT EXISTS notifications (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NOT NULL,
    title       VARCHAR(200) NOT NULL,
    message     TEXT,
    type        ENUM('success','info','warning','error') NOT NULL DEFAULT 'info',
    is_read     BOOLEAN NOT NULL DEFAULT FALSE,
    link        VARCHAR(500),
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_notif_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_notif_user (user_id),
    INDEX idx_notif_read (is_read)
) ENGINE=InnoDB;

-- ---------- api_keys ----------
CREATE TABLE IF NOT EXISTS api_keys (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NOT NULL,
    name        VARCHAR(150) NOT NULL,
    key_hash    VARCHAR(128) NOT NULL UNIQUE,
    last_used_at DATETIME,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_apikey_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_apikey_user (user_id)
) ENGINE=InnoDB;

-- ---------- logs ----------
CREATE TABLE IF NOT EXISTS logs (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT,
    action      VARCHAR(80) NOT NULL,
    description VARCHAR(500),
    ip_address  VARCHAR(45),
    user_agent  VARCHAR(255),
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_log_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_log_user (user_id),
    INDEX idx_log_action (action),
    INDEX idx_log_created (created_at)
) ENGINE=InnoDB;