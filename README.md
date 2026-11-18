# Progressive Rummy, fifth edition (update 4)

**What's new in update 4:** the round's goal is about twice as big on a computer, and it stands to the left of your card holder, level with your top and bottom rows. Your name and the line that tells you what to do sit just above it. On a phone the goal stays right under your name, a bit bigger than before. On the table picture, "Progressive Rummy" is a little smaller and CHAMPIONSHIP is bigger, so the two are close to the same size; "Thom Joe's" is just as you drew it. And the **What happened** list under the scores starts clean every time a round is dealt, including the first round of a new game.

**Update 3:** the round's goal sits right next to your cards now, not on the table. On a computer it's in a gold-edged sign between your name and the line that tells you what to do, just above your card holder. On a phone it's right under your name, and while your cards are scrolled off the screen, the goal shows on the **Your cards** button at the bottom. Also, when you move more cards up to a top row that already has cards in it, the new cards start a group of their own beside the cards already there, instead of mixing in with them. While you drag a card up, a **New group** spot shows at the right end of the top row; drop the card there. Dropping it right on a card in the top row still puts it in that spot.

**Update 2:** the table uses your own design, Thom Joe's Progressive Rummy. The red leather covers the table, and the gold crown and rings sit right under the draw pile and the discard pile. CHAMPIONSHIP is added in gold in the outer ring, under "Progressive Rummy". Your four card suits sit in the corners of the table. On a smaller computer screen, the bottom of the writing can go under the turn messages, so the whole table still fits without scrolling.

**From update 1:** both rows of your card holder are now the same size, and the holder sits in the middle of the table in front of you instead of stretching out to both sides. The writing on the light parts of the table is black, so it's easy to read. And there's an **Exit game** button, so you can leave a game without closing the browser.

The fifth edition gave the game a table like the mahjong table picture: a tan wooden edge, and a round middle where the draw pile and the discard pile sit. There are no mahjong tiles: everything is cards. Your hand now stands in a **card holder with two rows**, a top row and a bottom row, and you can move each card up, down and around however you like. When you lay down, your cards go face up on the felt right in front of your holder. The rules, the scoring, your groups and everything else from the fourth edition work the same way.

It still runs on your desktop computer, and people in your house join from their phones on the same Wi-Fi.

## Getting it onto your desktop

Do these steps on the **desktop computer**, not on your phone. A file opened on the phone, or through Phone Link, lands on the phone, and the game can't run there.

1. On the desktop, open the Sesame website and go to the chat with me.
2. Click the file called **progressive_rummy_5th_edition_update3.zip**, then click **Download**.
3. Open your **Downloads** folder. You'll see the zip file there.
4. **Right-click** the zip file and choose **Extract All**. Then click **Extract**. (Double-clicking the zip only peeks inside it.)
5. A new folder opens called **Progressive Rummy 5th edition update 4**.

I can't put files on your computer myself, so these steps are yours to do.

## Starting the game

1. If an older version is still running, close its black window first. Only one copy can run at a time. The game you were playing can't move over to the new version, so you start a fresh game.
2. In the new folder, double-click **Start Progressive Rummy.bat**.
3. A black window opens. Your web browser should open the game by itself. If it doesn't, type `http://localhost:8000` into the browser's address bar.
4. If Windows asks whether Python can use the network, click **Allow**. Without it, phones can't join.
5. Leave the black window open while you play. Closing it ends the game.

If the black window says the game is already running, close the other black window and double-click the .bat file again.

You can delete the old folder and the old zip whenever you like. The new folder has everything.

## Getting everyone to the table

1. On the computer, type your name and click **Start a new table**. You get a four-letter table code, and under it a link that starts with your computer's Wi-Fi address, like `http://192.168.1.25:8000/?table=ABCD`.
2. On each phone, open the web browser (Safari on an iPhone, Chrome on an Android) and type that link. The code fills itself in. Or type the second address from the black window and then the code. Don't use an address with **localhost** in it on a phone: that only works on the computer.
3. Each player types their name and taps **Join table**.

An iPhone needs nothing installed. It's a web page, the same as on an Android. The phone just has to be on the same Wi-Fi as your computer.

People get 30 seconds to join, and the clock starts over once. After that, computer players take the empty seats for the whole game. To play right away, tap **Deal now, with computer players in the empty seats**.

## What the table looks like

- **The table** is red felt with a tan wooden edge, like your picture.
- **The middle of the table** holds the draw pile (blue card backs) and the discard pile, on the gold crown and rings.
- **This round's goal** (for example "2 sets of 3") is in a big gold-edged sign right by your cards: to the left of your card holder on a computer, under your name on a phone.
- **The other players sit around the table:** one across from you, one on each side. Each one has a name plate with their score, how many cards they hold, and a tag that says **Goal laid down** or **Not down yet**. Their cards stand in a cream-colored holder, backs toward you, so you can see how many they hold but never what they are.
- **Each player's cards on the table sit on the felt right in front of their own seat**, in their own color, with their name on top: "Betty's cards on the table". When someone adds a card to your set, it stays in front of you.
- **Your card holder is along your edge of the table**, at the bottom, with your own place on the felt just above it.
- **On a computer, the whole table fits in the browser window.** It shrinks a little when the window is small, so you don't scroll up and down. Make the window bigger and it grows back.
- **On a phone, the table is one long page** you scroll up and down. When your cards are off the bottom of the screen, a **Your cards** button sits in the corner; tap it to jump down to your hand. On your turn it glows gold and says **Your turn**. The buttons under your hand sit two to a row and are big enough for a thumb.
- **Whose turn it is** shows three ways: the strip along the top, the gold sign in the middle of the table, and a glow around that player's seat. You hear a chime when it's your turn.

## Following the computer players

- **Under each player's name** a line says what they did: "This turn:" while they play, then "Last turn:" until their next turn. For example: "Last turn: drew from the pile → added 7♣ to Sam's Run 3 to 7 ♣ → discarded K♦".
- **The discard pile** says who threw the top card, for example "Betty discarded this".
- **Cards someone else put on the table since your last turn** have a green outline, and their group says NEW.
- **What happened**, on the right under the scores, lists every move with the newest at the top.
- **Computers: normal speed** at the top switches to **Computers: slower**, which gives them about twice as long between moves. Tap it again to go back.

You never see a card someone drew from the pile, or anyone else's hand.

## Playing your turn

The middle of the table shows the three steps and lights up the one you're on: **1 Draw**, **2 Lay down or add**, **3 Discard one**. The message box above your hand always says what to do next, and the buttons under your hand say exactly what they will do.

1. **Draw.** Tap **Draw from the pile**, or tap the top card of the discard pile to take it. You can take the discard before or after you've laid down. You get one draw a turn, and only the top card. The card you drew says NEW.
2. **Lay down your goal**, if you can. Tap each card for your goal, so it rises up. Then tap **Lay down my goal**. You don't have to sort the cards into groups: the game works that out. If you're not sure you have it, tap **Find my goal for me** and it picks the cards for you.
3. **After your goal is down**, on this turn or a later one:
   - **Add a card to any group:** tap one card. Every group it fits on glows gold, yours or anyone else's. Tap a glowing group. Deuces and jokers work too.
   - **Put down a new group,** like three nines: tap the cards, then tap **Put down as a new group**.
4. **Discard.** Tap **one** card, then tap the red **Discard** button, or tap the discard pile. Your turn ends.

If you tapped too many cards, tap **Clear picked cards** and start over. If a move isn't allowed, a message says why and what to do instead.

To go out, play your cards until one is left, then discard it.

## Your card holder

Your cards stand in a holder with **two rows**: a **top row** and a **bottom row**. It works like the racks on your picture's table, where you slide pieces around to set up your hand. Both rows are the same size, and the holder sits in the middle of your edge of the table, so your cards are right in front of you. On a phone, both rows use the full width of the screen.

- **The deal goes in the bottom row**, and so does every card you draw. The top row starts empty.
- **Move cards up or down:** tap the cards so they rise, then tap **▲ Up a row** or **▼ Down a row** under your hand. Or drag a card from one row to the other: with the mouse on a computer, or on a phone press and hold the card for a moment, then slide it.
- **Cards moved up start their own group:** if the top row already has cards, say a run you've set up, the cards you move up go into a new group beside it, so your run stays together. When you drag, drop on the **New group** spot at the right end of the top row, or right on a card to put it in that exact place.
- **Move one card at a time, anywhere:** drag it in front of any card in either row. Or tap one card and use the left and right arrows.
- **How you use the rows is up to you.** For example, put the sets you're building in the top row and leave the cards you don't need yet in the bottom row.
- **Only you see your holder.** Nothing about how you arrange it goes to the table, and it doesn't change what you're allowed to play. Everyone gets the same kind of holder on their own screen.

**Laying down is separate from arranging.** Arranging only moves cards inside your holder. When your whole goal is ready, pick the cards and tap **Lay down my goal**, or drag them up onto your place on the felt, just above your holder; it glows green while you drag. You still have to lay down the whole goal at once, the same as before.

**Dragging onto the table** works for the other moves too, on your turn: drag one card onto a group that glows green to add it there, or onto the discard pile to discard it. The buttons still work the same way if you'd rather tap.

## Grouping your hand

You can split your hand into groups, the way you'd slide cards around in your hand at the kitchen table: six cards for a run here, three for a set there, the rest loose. **Only you see your groups.** The other players' screens never find out, and the groups don't change what you're allowed to play.

**The easy way (tap):**

1. Tap the cards you want together, so they rise up.
2. Tap **Make a group** under your hand. They move into their own box called Group 1.
3. To put more cards in a group, tap them, then tap **Move here** on that group's box (it says how many, like **Move 2 here**).
4. To change the order, tap one card, then tap the left or right arrow under your hand.
5. To undo a group, tap the **✕** on its box. Its cards go back with the loose cards in the same row. **Break up all groups** undoes them all.
6. A group can sit in either row. Tap the **▲** or **▼** on its box to move the whole group to the other row, or drag it by its name.

**Dragging (computer):** drag a card with the mouse onto another card, onto a group, onto the other row, or onto **Drop here for a new group**, which shows up while you drag. If you drag a card you've picked, all your picked cards move together.

**Dragging (phone):** press and hold a card for a moment, then slide it where you want it. A quick swipe just scrolls the page.

**Good to know:**

- **Pick these** on a group picks all its cards, handy for laying down or putting down a new group.
- A card you draw joins the loose cards in the bottom row and says NEW. Cards you play or throw away leave their group.
- **Sort by rank** and **Sort by suit** sort inside each group and each row, and keep your groups and rows.
- Your groups and rows stay if you reload the page. A new round starts with no groups and the whole deal in the bottom row.

## The score

On the computer, the scoreboard is on the right. On a phone, tap **Scores** at the top. Points are the cards left in your hand when someone goes out: joker 50, deuce 25, ace 15, face cards 10, every other card 5. Lowest total after round 16 wins.

Under the scores, **What happened** lists what everyone did this round. It starts clean each time a new round is dealt.

The **Sound on** button at the top turns the sounds off.

## Your house rules in this version

- Cards dealt and each round's goal come from your rule sheet. Sixteen rounds.
- Two decks with four jokers. Deuces and jokers are wild, with no more than two wilds in one group.
- You must hold the whole goal before you lay any of it down.
- Each turn you draw once: the top of the draw pile or the top discard, before or after you've laid down.
- After you lay down, you can add cards, wilds included, to anyone's sets and to either end of anyone's run.
- After you lay down, you can put down more new sets and runs for the rest of the round.
- A spot a wild holds stays closed. A real card can't take it.
- Aces go low (A-2-3-4) or high (J-Q-K-A), but a run can't wrap around (no K-A-2).
- You go out only by discarding your last card.

## One rule to check

When we first went over your rules, you said that after you lay down you draw from the pile. When you tested the second edition, you asked to take the discard after laying down too, so this version allows it. If your table plays the first way, the person who made the table can untick **After laying down, players may take the top discard**, under What happened on the right. Everyone sees the change.

## Guesses you can correct

I had to guess these. Tell me if your table plays any of them differently.

- A new extra set needs at least 3 cards, and a new extra run at least 4.
- When you add a wild to the end of a run, it goes on the high end if there's room, otherwise the low end.
- Nobody can go out on their first turn of a round.
- You can add cards on the same turn you lay down your goal.
- When the draw pile runs out, the discards, except the top card, are shuffled into a new pile.
- Dealing without computer players needs at least two people.
- Between rounds, anyone at the table taps the button to deal the next round.

## Leaving a game

Click **Exit game** at the top of the screen (in the waiting room it's **Leave this table**). The game asks first, so a slip of the finger doesn't throw you out: click **Yes, exit the game**, or **No, stay at the table** to keep playing.

- **Before the cards are dealt,** your seat opens up for someone else.
- **During a game,** a computer player takes over your seat, your cards and your score for the rest of that game, so everyone else can keep playing. You can't come back into that same game.
- **If you're the only person at the table,** leaving ends that game.
- **Afterwards** you're back at the start screen in the same browser window, and you can start a new table or join another one.
- If you made the table, the switch for the table rules passes to the next person at the table.

The black window keeps running, so friends can keep playing. To stop the whole program, close the black window as before.

## What this version can't do yet

- **Play over the internet.** Everyone has to be on your home Wi-Fi. Putting the game on a website for friends in other houses is on the list for later.
- **Save a game.** If the black window closes, the game in progress is lost.
- **Play well as a computer.** The computer players are simple. They now take a discard that fits a group on the table, but they sometimes still get stuck in the rounds with long runs, and a hand that goes on far too long stops without scoring.
- **Chat at the table.** That's on the list for a later version.

## Files in this folder

- `Start Progressive Rummy.bat`: starts the game.
- `server.py`, `game.py`, `rummy.py`: the Python program.
- `static`: the web page, its look and its sounds.
- `test_...py` files and the `dev_tests` folder: checks I ran to make sure it works. You can ignore them.
