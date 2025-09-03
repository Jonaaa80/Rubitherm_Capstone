## Field extracted
* customer first name
* customer last name
* customer role
* company name
* website
* company address
* customer email
* customer phone
* message 

## Core Logic 
1. we are reading the email from the very bottom to the stopper (signature block)
2. We are using '@rubitherm.' as an anchor
    A : we ignore the anchor (+-1 line)
    B : we use the anchor to extract information 
3. There are 2 types of emails we are handling and the method is also printed
    A : Website form inquiry -> handled by 'form_inquiry_extractor'
    B : Customer direct email inquiry -> handled by 'direct_email_extractor'

## Form_inquiry_extractor
1. We find a block with 'Name:' ~ 'Country:' and extract information 
2. We extract information are only in the website inquiry format
    "first_name": "Matthias",
    "last_name": "Moser",
    "company": "Moser Konstruktion GmbH &",
    "customer_phone": "0491721442009",
    "email": "m.moser@moser-konstruktion.de",
    "address": "Deutschland", 
    "message": "..."
3. Information not included are
    "roles": list(set(roles)),
    "website": list(set(websites)),

## Direct_email_extractor 
1. For customer_phone, email, website : use Regex
2. For Person(person name), ORG(company), role, GPE,LOC(address) : use Spacy
