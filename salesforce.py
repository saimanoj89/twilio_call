from simple_salesforce import Salesforce
from mailchimp_marketing import Client
from mailchimp_marketing.api_client import ApiClientError
from faker import Faker

fake= Faker()

# ---------- Salesforce Setup ----------
sf = Salesforce(
    username="saimanojv852@agentforce.com",
    password="Sm@8978909879",
    security_token="J7LKO4Fu8cZfdVc0YdKnAAna"
)

def createContact():
    fname=fake.first_name()
    lname=fake.last_name()
    email=fake.email().lower()

    employee=   sf.Contact.create({
        'FirstName': fname,
        'LastName': lname,
        'Email': email
    })
    print("✅ Created Salesforce Contact:", employee['id'])

# for i in range(1,500):
#     createContact()

result = sf.query("""
    SELECT Id, FirstName, LastName, Email 
    FROM Contact 
   
""")

contacts=[]

for record in result['records']:
    contacts.append({
        "salesforce_emp_id": record['Id'],
        "firstname":record['FirstName'],
        "lastname":record['LastName'],
        "email":record['Email']
    })

print(len(contacts))
