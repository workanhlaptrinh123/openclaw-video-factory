# Privacy Policy & User Data Deletion — OpenClaw Video Factory

**Last updated:** November 27, 2026  
**Contact:** workanhlaptrinh123@gmail.com  

## 1. Overview
OpenClaw Video Factory is a local desktop automation tool that helps content creators generate short-form videos and publish approved videos to their own connected platforms (Google Drive, Google Sheets, YouTube, and Facebook Pages).

## 2. Data We Collect and Store
- **Local-only storage:** All OAuth access tokens, refresh tokens, API keys, generated videos, and configuration files are stored **exclusively on the user's own computer** (`<openclaw_state_dir>/video-factory/secrets/`).
- **No external server storage:** OpenClaw Video Factory does not operate any remote database and never transmits, sells, or shares user tokens or personal data to third parties.
- **Permissions used:**
  - **Facebook (`pages_show_list`, `pages_read_engagement`, `pages_manage_posts`):** Used only to list the Facebook Pages managed by the authenticated user and publish user-approved videos to the Page chosen by the user.
  - **Google (`drive.file`, `spreadsheets`, `youtube.upload`):** Used only to create/update the user's own approval spreadsheet, upload videos created by the app to the user's Google Drive, and upload user-approved videos to the user's YouTube channel.

## 3. User Data Deletion Instructions
Because OpenClaw Video Factory stores all credentials locally on your computer, you can delete all of your data immediately at any time by following these steps:

1. **Delete local credentials on your PC:** Delete the folder `<openclaw_state_dir>\video-factory\secrets\` (or uninstall OpenClaw Video Factory).
2. **Revoke Facebook access:** Go to **Facebook Settings & Privacy → Settings → Business Integrations** (or **Apps and Websites**), find **OpenClaw Video Factory**, and click **Remove**.
3. **Revoke Google access:** Go to https://myaccount.google.com/permissions, find **OpenClaw Video Factory**, and click **Remove Access**.

If you have any questions or need assistance deleting your data, email us at **workanhlaptrinh123@gmail.com**.
