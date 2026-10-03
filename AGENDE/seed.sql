-- =========================================================
-- AGENDE SEED DATA
-- Run this AFTER schema.sql
-- =========================================================

USE agende_db;

-- ---------------------------------------------------------
-- ROLES
-- ---------------------------------------------------------
INSERT INTO roles (id, name) VALUES
(1, 'user'),
(2, 'provider'),
(3, 'admin');

-- ---------------------------------------------------------
-- USERS
-- Passwords below are hashed with Werkzeug.
-- admin123   -> admin@agende.com
-- provider123-> provider@agende.com (and other providers use password123)
-- user123    -> user@agende.com (and other users use password123)
-- password123 is used for all extra sample accounts.
-- ---------------------------------------------------------

-- Admin account
INSERT INTO users (role_id, name, email, password, phone, is_active) VALUES
(3, 'Angela Marasigan', 'admin@agende.com', 'scrypt:32768:8:1$8NXNaoqGgXyIN5gh$7fe7e5893670e0f1488dc2dac7960fcc674b651c8668a45c08556eaedef7426a518f31948d6d93ee1dbd822b71c7008bee27d16af6ee7449a0a82c5014586c28', '0917-100-0001', 1);

-- Provider accounts (linked to providers table below)
INSERT INTO users (role_id, name, email, password, phone, is_active) VALUES
(2, 'Dr. Miguel Santos', 'provider@agende.com', 'scrypt:32768:8:1$pP5MW5mdC3v5FlbO$83f964b5a105f7fbb1cf768a8269e263ad70f17d5533c9f47087c07e1cc9ffefdc273d2296ba8e1abbb44c636f433e2a8911bb4bf7b0b7688bd2503bf5589d3a', '0917-200-0001', 1),
(2, 'Dr. Karen Villareal', 'karen.villareal@agende.com', 'scrypt:32768:8:1$usDorqSnQrOYOjMa$70f11cc50e07f16ce0af5a138b1caf112882fff173ffbbe050511000d41ffbaf88393d37e31b9c078609634e3faa3554985bf55969ce9ba99f6e2bd554aaed57', '0917-200-0002', 1),
(2, 'Engr. Paolo Reyes', 'paolo.reyes@agende.com', 'scrypt:32768:8:1$usDorqSnQrOYOjMa$70f11cc50e07f16ce0af5a138b1caf112882fff173ffbbe050511000d41ffbaf88393d37e31b9c078609634e3faa3554985bf55969ce9ba99f6e2bd554aaed57', '0917-200-0003', 1);

-- Client / user accounts
INSERT INTO users (role_id, name, email, password, phone, is_active) VALUES
(1, 'Juan Dela Cruz', 'user@agende.com', 'scrypt:32768:8:1$9pkw84xm3i8nBBlR$0d3462b7ea95c4e6a409ec00c6398a340d45b247065f01f431d8ca70e2b6e670ac8977db5da8dbd41d110800877e2a7afae981ef29722c389b4d6a4f94e12fa8', '0917-300-0001', 1),
(1, 'Maria Clara Santos', 'maria.santos@example.com', 'scrypt:32768:8:1$usDorqSnQrOYOjMa$70f11cc50e07f16ce0af5a138b1caf112882fff173ffbbe050511000d41ffbaf88393d37e31b9c078609634e3faa3554985bf55969ce9ba99f6e2bd554aaed57', '0917-300-0002', 1),
(1, 'Jose Rizal Ramos', 'jose.ramos@example.com', 'scrypt:32768:8:1$usDorqSnQrOYOjMa$70f11cc50e07f16ce0af5a138b1caf112882fff173ffbbe050511000d41ffbaf88393d37e31b9c078609634e3faa3554985bf55969ce9ba99f6e2bd554aaed57', '0917-300-0003', 1),
(1, 'Andres Bonifacio Cruz', 'andres.cruz@example.com', 'scrypt:32768:8:1$usDorqSnQrOYOjMa$70f11cc50e07f16ce0af5a138b1caf112882fff173ffbbe050511000d41ffbaf88393d37e31b9c078609634e3faa3554985bf55969ce9ba99f6e2bd554aaed57', '0917-300-0004', 1),
(1, 'Gabriela Silang Torres', 'gabriela.torres@example.com', 'scrypt:32768:8:1$usDorqSnQrOYOjMa$70f11cc50e07f16ce0af5a138b1caf112882fff173ffbbe050511000d41ffbaf88393d37e31b9c078609634e3faa3554985bf55969ce9ba99f6e2bd554aaed57', '0917-300-0005', 1),
(1, 'Emilio Aguinaldo Reyes', 'emilio.reyes@example.com', 'scrypt:32768:8:1$usDorqSnQrOYOjMa$70f11cc50e07f16ce0af5a138b1caf112882fff173ffbbe050511000d41ffbaf88393d37e31b9c078609634e3faa3554985bf55969ce9ba99f6e2bd554aaed57', '0917-300-0006', 1),
(1, 'Melchora Aquino Flores', 'melchora.flores@example.com', 'scrypt:32768:8:1$usDorqSnQrOYOjMa$70f11cc50e07f16ce0af5a138b1caf112882fff173ffbbe050511000d41ffbaf88393d37e31b9c078609634e3faa3554985bf55969ce9ba99f6e2bd554aaed57', '0917-300-0007', 1),
(1, 'Antonio Luna Bautista', 'antonio.bautista@example.com', 'scrypt:32768:8:1$usDorqSnQrOYOjMa$70f11cc50e07f16ce0af5a138b1caf112882fff173ffbbe050511000d41ffbaf88393d37e31b9c078609634e3faa3554985bf55969ce9ba99f6e2bd554aaed57', '0917-300-0008', 1);

-- ---------------------------------------------------------
-- SERVICES
-- ---------------------------------------------------------
INSERT INTO services (id, name, description, duration, is_active) VALUES
(1, 'General Consultation', 'Basic check-up and consultation', 30, 1),
(2, 'Dental Cleaning', 'Routine dental cleaning and check-up', 45, 1),
(3, 'IT Support Session', 'Technical support and troubleshooting', 60, 1),
(4, 'Legal Consultation', 'Consultation with a legal advisor', 30, 1),
(5, 'Career Counseling', 'One-on-one career guidance session', 45, 1);

-- ---------------------------------------------------------
-- PROVIDERS (linked to provider user accounts)
-- users.id 2 = Dr. Miguel Santos, 3 = Dr. Karen Villareal, 4 = Engr. Paolo Reyes
-- ---------------------------------------------------------
INSERT INTO providers (id, user_id, service_id, is_active) VALUES
(1, 2, 1, 1),
(2, 3, 2, 1),
(3, 4, 3, 1);

-- ---------------------------------------------------------
-- PROVIDER SCHEDULES
-- day_of_week: 0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday, 5=Saturday, 6=Sunday
-- ---------------------------------------------------------
INSERT INTO provider_schedules (provider_id, day_of_week, start_time, end_time, is_available) VALUES
(1, 0, '08:00:00', '17:00:00', 1),
(1, 1, '08:00:00', '17:00:00', 1),
(1, 2, '08:00:00', '17:00:00', 1),
(1, 3, '08:00:00', '17:00:00', 1),
(1, 4, '08:00:00', '17:00:00', 1),
(2, 0, '09:00:00', '18:00:00', 1),
(2, 2, '09:00:00', '18:00:00', 1),
(2, 4, '09:00:00', '18:00:00', 1),
(3, 1, '08:00:00', '16:00:00', 1),
(3, 3, '08:00:00', '16:00:00', 1),
(3, 5, '08:00:00', '12:00:00', 1);

-- ---------------------------------------------------------
-- APPOINTMENTS (sample data with different statuses/dates)
-- users.id 5 = Juan Dela Cruz (user@agende.com), 6-12 = other sample clients
-- ---------------------------------------------------------
INSERT INTO appointments (user_id, provider_id, service_id, appointment_date, start_time, end_time, status, notes, created_at) VALUES
(5, 1, 1, CURDATE(), '09:00:00', '09:30:00', 'confirmed', 'Follow-up check-up', NOW()),
(5, 2, 2, CURDATE(), '10:00:00', '10:45:00', 'pending', 'First time cleaning', NOW()),
(6, 1, 1, CURDATE(), '11:00:00', '11:30:00', 'confirmed', NULL, NOW()),
(7, 3, 3, DATE_ADD(CURDATE(), INTERVAL 1 DAY), '09:00:00', '10:00:00', 'pending', 'Laptop issues', NOW()),
(8, 2, 2, DATE_ADD(CURDATE(), INTERVAL 2 DAY), '09:00:00', '09:45:00', 'confirmed', NULL, NOW()),
(9, 1, 1, DATE_ADD(CURDATE(), INTERVAL 3 DAY), '08:30:00', '09:00:00', 'pending', NULL, NOW()),
(5, 3, 3, DATE_SUB(CURDATE(), INTERVAL 5 DAY), '08:00:00', '09:00:00', 'completed', 'Resolved network issue', NOW()),
(6, 2, 2, DATE_SUB(CURDATE(), INTERVAL 3 DAY), '10:00:00', '10:45:00', 'completed', NULL, NOW()),
(10, 1, 1, DATE_SUB(CURDATE(), INTERVAL 2 DAY), '13:00:00', '13:30:00', 'cancelled', 'Client requested cancellation', NOW()),
(11, 3, 3, DATE_SUB(CURDATE(), INTERVAL 1 DAY), '08:00:00', '09:00:00', 'completed', NULL, NOW()),
(12, 2, 2, DATE_ADD(CURDATE(), INTERVAL 4 DAY), '11:00:00', '11:45:00', 'pending', NULL, NOW()),
(5, 1, 1, DATE_ADD(CURDATE(), INTERVAL 6 DAY), '08:00:00', '08:30:00', 'confirmed', NULL, NOW());

-- ---------------------------------------------------------
-- APPOINTMENT HISTORY
-- ---------------------------------------------------------
INSERT INTO appointment_history (appointment_id, action, old_status, new_status, performed_by, created_at) VALUES
(1, 'created', NULL, 'pending', 5, NOW()),
(1, 'confirmed', 'pending', 'confirmed', 2, NOW()),
(7, 'created', NULL, 'pending', 5, NOW()),
(7, 'confirmed', 'pending', 'confirmed', 4, NOW()),
(7, 'completed', 'confirmed', 'completed', 4, NOW()),
(9, 'created', NULL, 'pending', 10, NOW()),
(9, 'cancelled', 'pending', 'cancelled', 10, NOW());

-- ---------------------------------------------------------
-- NOTIFICATIONS
-- ---------------------------------------------------------
INSERT INTO notifications (user_id, message, type, is_read, created_at) VALUES
(5, 'Your appointment for General Consultation has been confirmed.', 'success', 0, NOW()),
(5, 'Your appointment for Dental Cleaning is pending provider confirmation.', 'info', 0, NOW()),
(6, 'Your appointment for General Consultation has been confirmed.', 'success', 1, NOW()),
(2, 'You have a new pending appointment request.', 'info', 0, NOW()),
(4, 'You have a new pending appointment request.', 'info', 0, NOW()),
(1, 'New client registered: Maria Clara Santos.', 'info', 1, NOW());
