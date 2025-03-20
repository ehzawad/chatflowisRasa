def analyze_specific_word(filename, target_word):
    """Analyze specific target word appearance across lines in a file."""
    print(f"ANALYZING SPECIFIC WORD '{target_word}' IN FILE: {filename}")
    print("=" * 80)
    
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            lines = file.readlines()
        
        lines = [line.strip() for line in lines]
        
        print("\nORIGINAL LINES:")
        for i, line in enumerate(lines[:2]):
            print(f"Line {i+1}: {line}")
        
        # Get raw byte representation of both lines
        bytes_line1 = lines[0].encode('utf-8')
        bytes_line2 = lines[1].encode('utf-8')
        
        # Visual search for words that might be our target
        line1_words = lines[0].split()
        line2_words = lines[1].split()
        
        # Find visual matches in both lines
        matches_line1 = []
        matches_line2 = []
        
        for word in line1_words:
            if any(c in target_word for c in word):
                matches_line1.append(word)
                
        for word in line2_words:
            if any(c in target_word for c in word):
                matches_line2.append(word)
        
        print("\nPOTENTIAL VISUAL MATCHES:")
        print(f"Line 1: {', '.join(matches_line1)}")
        print(f"Line 2: {', '.join(matches_line2)}")
        
        # Check if we can find the raw bytes of target_word in both lines
        target_bytes = target_word.encode('utf-8')
        
        if target_bytes in bytes_line1:
            print(f"\nTarget word found in line 1 using byte search")
        else:
            print(f"\nTarget word NOT found in line 1 using exact byte search")
            
        if target_bytes in bytes_line2:
            print(f"Target word found in line 2 using byte search")
        else:
            print(f"Target word NOT found in line 2 using exact byte search")
        
        # Get positions of visually similar words
        import unicodedata
        
        def get_word_positions(line):
            positions = []
            for i, c in enumerate(line):
                if c in target_word:
                    start = i
                    # Expand to get the full word
                    while start > 0 and line[start-1] not in ' #':
                        start -= 1
                    end = i
                    while end < len(line)-1 and line[end+1] not in ' #':
                        end += 1
                    positions.append((start, end+1, line[start:end+1]))
            return positions
        
        positions1 = get_word_positions(lines[0])
        positions2 = get_word_positions(lines[1])
        
        # Find the best candidates
        best1 = None
        best2 = None
        
        for start, end, word in positions1:
            if target_word in word or target_word[0] in word:
                best1 = (start, end, word)
                break
                
        for start, end, word in positions2:
            if target_word in word or target_word[0] in word:
                best2 = (start, end, word)
                break
        
        if best1 and best2:
            word1 = best1[2]
            word2 = best2[2]
            
            print(f"\nANALYZING WORDS:")
            print(f"Line 1 word: '{word1}'")
            print(f"Line 2 word: '{word2}'")
            
            # Character by character comparison
            print("\nCHARACTER-BY-CHARACTER COMPARISON:")
            print("Pos | Char1 | Unicode1 | Bytes1 | Char2 | Unicode2 | Bytes2 | Same?")
            print("-" * 80)
            
            max_len = max(len(word1), len(word2))
            are_identical = True
            
            for i in range(max_len):
                if i < len(word1):
                    c1 = word1[i]
                    u1 = f"U+{ord(c1):04X}"
                    b1 = ' '.join(f'{b:02X}' for b in c1.encode('utf-8'))
                    try:
                        n1 = unicodedata.name(c1)[:15]
                    except:
                        n1 = "UNKNOWN"
                else:
                    c1 = "N/A"
                    u1 = "N/A"
                    b1 = "N/A"
                    n1 = "N/A"
                    
                if i < len(word2):
                    c2 = word2[i]
                    u2 = f"U+{ord(c2):04X}"
                    b2 = ' '.join(f'{b:02X}' for b in c2.encode('utf-8'))
                    try:
                        n2 = unicodedata.name(c2)[:15]
                    except:
                        n2 = "UNKNOWN"
                else:
                    c2 = "N/A"
                    u2 = "N/A"
                    b2 = "N/A"
                    n2 = "N/A"
                
                if i < len(word1) and i < len(word2):
                    same = "✓" if c1 == c2 else "✗"
                    if c1 != c2:
                        are_identical = False
                else:
                    same = "✗"
                    are_identical = False
                
                print(f"{i:3d} | {c1:5s} | {u1:8s} | {b1:15s} | {c2:5s} | {u2:8s} | {b2:15s} | {same}")
            
            # Full words comparison
            print("\nCOMPLETE WORD ENCODING COMPARISON:")
            bytes1 = word1.encode('utf-8')
            bytes2 = word2.encode('utf-8')
            
            print(f"Line 1: {' '.join(f'{b:02X}' for b in bytes1)}")
            print(f"Line 2: {' '.join(f'{b:02X}' for b in bytes2)}")
            
            # Conclusion
            print("\nCONCLUSION:")
            print("=" * 80)
            
            if bytes1 == bytes2:
                print("✓ The two instances have IDENTICAL byte representations")
                print("✓ VSCode should match both in searches")
                print("\nIf VSCode isn't matching both, possible reasons:")
                print("1. There might be surrounding context differences")
                print("2. The search settings might be using regex or case sensitivity")
                print("3. There could be a VSCode bug with complex scripts")
            else:
                print("✗ The two instances have DIFFERENT byte representations")
                print("✗ This explains why VSCode doesn't match both when searching")
                
                # Identify specific differences
                if len(bytes1) != len(bytes2):
                    print(f"- Different byte lengths: {len(bytes1)} vs {len(bytes2)}")
                
                for i, (b1, b2) in enumerate(zip(bytes1, bytes2)):
                    if b1 != b2:
                        print(f"- First difference at byte position {i}: {b1:02X} vs {b2:02X}")
                        break
                
                # Check for invisible characters
                has_special_chars = False
                for i, (c1, c2) in enumerate(zip(word1, word2)):
                    if c1 != c2:
                        cat1 = unicodedata.category(c1)
                        cat2 = unicodedata.category(c2)
                        
                        if cat1 in ['Mn', 'Mc', 'Me', 'Cf'] or cat2 in ['Mn', 'Mc', 'Me', 'Cf']:
                            has_special_chars = True
                            print(f"- Found at position {i}:")
                            print(f"  Line 1: '{c1}' (Category: {cat1})")
                            print(f"  Line 2: '{c2}' (Category: {cat2})")
                
                if has_special_chars:
                    print("- These appear to be combining characters or format controls")
                    print("- They affect visual rendering but have different encodings")
        else:
            print("\nCould not find suitable words to compare in both lines.")
    
    except Exception as e:
        import traceback
        print(f"Error: {str(e)}")
        print(traceback.format_exc())

# Call the function with file and target word
analyze_specific_word('hola.txt', 'জুনিয়র')
