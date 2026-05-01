-- Sample seed data for local development and testing

INSERT INTO properties (address, city, county, zip_code, distress_type, owner_name, parcel_id)
VALUES
    ('123 Elm St', 'Houston', 'Harris', '77001', 'foreclosure', 'Jane Doe', 'HCC-001-2024'),
    ('456 Oak Ave', 'San Antonio', 'Bexar', '78201', 'tax_delinquency', 'John Smith', 'BXR-002-2024'),
    ('789 Pine Rd', 'Dallas', 'Dallas', '75201', 'probate', NULL, 'DAL-003-2024'),
    ('321 Maple Dr', 'Austin', 'Travis', '78701', 'preforeclosure', 'Maria Garcia', 'TRV-004-2024');

-- TODO: Add sample property_events rows linked to the above properties
-- TODO: Add sample scores after scoring engine is implemented
