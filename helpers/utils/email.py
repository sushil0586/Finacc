from django.core.mail import EmailMessage

def send_invoice_email(subject, body, to_email, pdf_content, filename):
    email = EmailMessage(
        subject=subject,
        body=body,
        to=[to_email]
    )
    email.attach(filename, pdf_content, 'application/pdf')
    email.send(fail_silently=False)