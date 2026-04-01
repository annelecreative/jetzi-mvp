# Manual Smoke Test Steps

## Setup for internal MVP destinations

Run the app with:

```bash
export BASE_DESTINATION_LIMIT=3
flask --app web_app run --debug --host=:: --port=5000
```

## 1) Create Alert submits and goes to next page

1. Open `http://127.0.0.1:5000/` or `http://[::1]:5000/`.
2. Fill required fields, including at least one available departure day.
3. Click `Create Alert`.
4. Confirm navigation to `/alert-created` and check terminal logs include `POST /alerts/create hit`.

## 2) Referral link generates

1. On `/alert-created`, confirm email.
2. On `/alerts/activated`, verify the `Invite friends to unlock more destinations` section is visible.
3. Click `Copy` and confirm the copied URL is `/r/<code>`.

## 3) Referral credit increases destination limit

1. Open the copied referral link in a fresh private/incognito window.
2. Create and confirm the referred user's first alert with a different email.
3. Return to the referrer account and open create alert page.
4. Confirm helper text now shows increased limit (`Up to 4 destinations`).

## 4) Minimum days validation

1. Select 2 available departure days.
2. Enter `3` for minimum days.
3. Submit and confirm clear error appears:
   `Minimum trip length can't be greater than your selected available departure days (2).`
