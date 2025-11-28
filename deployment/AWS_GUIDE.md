# ☁️ Deploying Zepto Scraper to AWS EC2 (Free Tier)

Since you are new to this, here is a step-by-step guide to running your scraper on a free AWS server.

## 1. Create an AWS Account
1. Go to [aws.amazon.com/free](https://aws.amazon.com/free).
2. Create an account (you will need a credit card for identity verification, but you won't be charged if you stay within limits).
3. **Free Tier Limits:** You get 750 hours/month of `t2.micro` or `t3.micro` instances for the first 12 months. This is enough to run one server 24/7.

## 2. Launch a Server (EC2 Instance)
1. Log in to the **AWS Console**.
2. Search for **EC2** and click **Launch Instance**.
3. **Name:** `ZeptoScraper`
4. **OS Image:** Choose **Ubuntu Server 24.04 LTS** (Free tier eligible).
5. **Instance Type:** Choose `t2.micro` (or `t3.micro` if available/free in your region).
6. **Key Pair:** Click **Create new key pair**.
   - Name: `zepto-key`
   - Type: `RSA`
   - Format: `.pem` (for Mac/Linux)
   - **Download** the file and keep it safe!
7. **Network Settings:** Ensure "Allow SSH traffic from" is checked (Anywhere 0.0.0.0/0 is easiest for now).
8. **Storage:** Set to **30 GB** (Free tier allows up to 30GB).
9. Click **Launch Instance**.

## 3. Connect to the Server
1. Open your Mac Terminal.
2. Move the key to a safe folder (e.g., `~/.ssh/`):
   ```bash
   mv ~/Downloads/zepto-key.pem ~/.ssh/
   chmod 400 ~/.ssh/zepto-key.pem
   ```
3. Get your instance's **Public IPv4 address** from the AWS Console.
4. Connect via SSH:
   ```bash
   ssh -i ~/.ssh/zepto-key.pem ubuntu@<YOUR_INSTANCE_IP>
   ```
   *(Type `yes` if asked to continue connecting)*

## 4. Upload Your Code
You can use `scp` (Secure Copy) to upload your project folder from your Mac to the server.
Run this **from your Mac terminal** (not the server terminal):

```bash
# Make sure you are in the project folder
cd /Users/ejazanwar/Desktop/Zepto_scrapper_final

# Upload files (excluding venv and data to save time)
scp -i ~/.ssh/zepto-key.pem -r . ubuntu@13.48.149.52:~/zepto_scraper
```

## 5. Setup and Run
1. Go back to your **Server Terminal** (SSH session).
2. Go into the folder:
   ```bash
   cd zepto_scraper
   ```
3. Make the setup script executable and run it:
   ```bash
   chmod +x deployment/setup_aws.sh
   ./deployment/setup_aws.sh
   ```
   *(This will take a few minutes to install Python, Playwright, etc.)*

4. **Run the Scraper:**
   ```bash
   source venv/bin/activate
   python3 zepto_tracker_test.py
   ```

## 6. Run Automatically (Optional)
To run it every day automatically, use `cron`:
1. Open crontab: `crontab -e`
2. Add this line to run at 8:00 AM daily:
   ```

## 7. Changing the Schedule or File
To change the timing or the script being run later:

1. **Connect to the server:**. -- 13.48.149.52
   ```bash
   ssh -i ~/.ssh/zepto-key.pem ubuntu@13.48.149.52
   ```

2. **Edit the cron schedule:**
   ```bash
   crontab -e
   ```
   *(If asked, choose `nano` as the editor by pressing `1` and `Enter`)*

3. **Modify the line:**
   You will see a line like this:
   ```bash
   30 0,2,4,6,8,10,12,14,16,18,20 * * * cd /home/ubuntu/zepto_scraper && /home/ubuntu/zepto_scraper/venv/bin/python3 zepto_tracker_test.py >> ...
   ```
   - **To change timing:** Edit the numbers at the start. Use [crontab.guru](https://crontab.guru/) to help generate the numbers.
   - **To change file:** Change `zepto_tracker_test.py` to your new filename.

4. **Save and Exit:**
   - Press `Ctrl + O`, then `Enter` to save.
   - Press `Ctrl + X` to exit.

5. **Verify:**
   Run `crontab -l` to see your changes.

## 8. Updating Your Code
If you make changes to the code on your laptop, you need to send the new files to the server.

**Run this from your Mac terminal:**

1. **Update a single file:**
   ```bash
   scp -i ~/.ssh/zepto-key.pem zepto_tracker_Arcade_Gloria.py ubuntu@13.48.149.52:~/zepto_scraper/
   ```

2. **Update everything (careful!):**
   ```bash
   scp -i ~/.ssh/zepto-key.pem -r . ubuntu@13.48.149.52:~/zepto_scraper/
   ```
   *(Note: This might overwrite your database if you have a local copy. It's usually safer to upload specific files.)*
