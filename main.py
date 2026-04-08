from agent import create_scheduler_agent

def main():
    print("=" * 55)
    print("  AI Meeting Scheduler — Powered by LangChain + Gemini")
    print("=" * 55)
    print("Examples:")
    print('  "Schedule a 1-hour Team Sync tomorrow at 10am"')
    print('  "Book a 30-minute standup at 9am this Saturday"')
    print('  "Set up a 45-min call with raj@example.com on Monday at 3pm"')
    print('  "Which days am I free this week?"')
    print('  "What was my busiest day this month?"')
    print('  "How many hours of meetings do I have this week?"')
    print('\nType "exit" to quit.\n')

    agent = create_scheduler_agent()

    while True:
        try:
            user_input = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "bye"):
            print("Goodbye!")
            break

        try:
            result = agent(user_input)
            print(f"\nAssistant: {result}\n")
        except Exception as e:
            print(f"\n[Error] {e}\n")


if __name__ == "__main__":
    main()